import math

import BigWorld
import GUI
from CurrentVehicle import g_currentPreviewVehicle
from Vehicle import SegmentCollisionResultExt
from gui.shared.utils.functions import makeTooltip
from gui.shared.utils.scheduled_notifications import Notifiable, PeriodicNotifier

from helpers import dependency
from AvatarInputHandler import cameras
from items import vehicles
from skeletons.gui.app_loader import IAppLoader
from skeletons.gui.shared.utils import IHangarSpace
from vehicle_systems.model_assembler import collisionIdxToTrackPairIdx
from vehicle_systems.tankStructure import TankPartIndexes


class ArmoryCheckerService(object):
    __hangarSpace = dependency.descriptor(IHangarSpace)
    __appLoader = dependency.descriptor(IAppLoader)

    __slots__ = ('__isEnabled', '__isShow', '__notificatorManager', '__currentCollisions', '__currentCursorPos')

    def __init__(self):
        super(ArmoryCheckerService, self).__init__()
        self.__isEnabled = False
        self.__isShow = False
        self.__notificatorManager = Notifiable()
        self.__currentCollisions = []
        self.__currentCursorPos = None

    def init(self):
        g_currentPreviewVehicle.onSelected += self.__onSelected
        self.__notificatorManager.addNotificator(PeriodicNotifier(lambda: 0.5, self.__checkCollision))

    def fini(self):
        self.__notificatorManager.clearNotification()
        if self.__isShow:
            self.__hideTooltip()

        if self.__isEnabled:
            self.__stopChecker()
            self.__isEnabled = False

        g_currentPreviewVehicle.onSelected -= self.__onSelected

    def __onSelected(self):
        self.__isEnabled = g_currentPreviewVehicle.item is not None
        if not self.__isEnabled and self.__isShow:
            self.__hideTooltip()

        if self.__isEnabled:
            self.__runChecker()
        else:
            self.__stopChecker()

    def __showTooltip(self):
        self.__isShow = True
        firstCol = self.__currentCollisions[0]
        self.__appLoader.getApp().getToolTipMgr().onCreateComplexTooltip(
            makeTooltip(
                body='part: {}\narmor: {}\np. armor: {}'.format(
                    TankPartIndexes.getName(firstCol.compName), firstCol.matInfo.armor,
                    _computePenetrationArmor(
                        firstCol.hitAngleCos if firstCol.matInfo.useHitAngle else 1.0, firstCol.matInfo)
                )
            ), 'INFO')

    def __hideTooltip(self):
        self.__isShow = False
        self.__appLoader.getApp().getToolTipMgr().hide()

    def __updateTooltip(self):
        firstCol = self.__currentCollisions[0]
        self.__appLoader.getApp().getToolTipMgr().hide()
        self.__appLoader.getApp().getToolTipMgr().onCreateComplexTooltip(
            makeTooltip(
                body='part: {}\narmor: {}\np. armor: {}'.format(
                    TankPartIndexes.getName(firstCol.compName), firstCol.matInfo.armor,
                    _computePenetrationArmor(
                        firstCol.hitAngleCos if firstCol.matInfo.useHitAngle else 1.0, firstCol.matInfo)
                )
            ), 'INFO')

    def __runChecker(self):
        self.__notificatorManager.startNotification()

    def __stopChecker(self):
        self.__currentCursorPos = None
        self.__currentCollisions = []
        self.__notificatorManager.stopNotification()

    def __checkCollision(self):
        cursorPosition = GUI.mcursor().position if (GUI.mcursor().inWindow and GUI.mcursor().inFocus and
                                                    self.__hangarSpace.isCursorOver3DScene) else None
        if self.__currentCursorPos != cursorPosition:
            self.__currentCollisions = []
            ray, wpoint = cameras.getWorldRayAndPoint(cursorPosition.x, cursorPosition.y)
            vehicle = BigWorld.entities[g_currentPreviewVehicle.vehicleEntityID]
            if vehicle.appearance.collisions is not None:
                collisions = vehicle.appearance.collisions.collideAllWorld(wpoint, wpoint + ray * 500)
                if collisions:
                    for collision in collisions:
                        matInfo = getMatinfo(vehicle, collision[3], collision[2])
                        if matInfo:
                            self.__currentCollisions.append(
                                SegmentCollisionResultExt(collision[0], collision[1], matInfo, collision[3]))
            if self.__currentCollisions and self.__isShow:
                self.__updateTooltip()
            elif self.__currentCollisions and not self.__isShow:
                self.__showTooltip()
            elif not self.__currentCollisions and self.__isShow:
                self.__hideTooltip()

        self.__currentCursorPos = cursorPosition


def getMatinfo(entity, parIndex, matKind):
    matInfo = None

    if parIndex == TankPartIndexes.CHASSIS:
        matInfo = entity.typeDescriptor.chassis.materials.get(matKind)
    elif parIndex == TankPartIndexes.HULL:
        matInfo = entity.typeDescriptor.hull.materials.get(matKind)
    elif parIndex == TankPartIndexes.TURRET:
        matInfo = entity.typeDescriptor.turret.materials.get(matKind)
    elif parIndex == TankPartIndexes.GUN:
        matInfo = entity.typeDescriptor.gun.materials.get(matKind)
    elif parIndex > len(TankPartIndexes.ALL):
        trackPairIdx = collisionIdxToTrackPairIdx(parIndex, entity.typeDescriptor)
        if trackPairIdx is not None:
            matInfo = entity.typeDescriptor.chassis.tracks[trackPairIdx].materials.get(matKind)
    elif entity.typeDescriptor.type.isWheeledVehicle and entity.appearance.collisions is not None:
        wheelName = entity.appearance.collisions.getPartName(parIndex)
        if wheelName is not None:
            # procedurally generated wheels have no material,
            # but they are monolithic and their armor is specified in wheel config
            matInfo = entity.typeDescriptor.chassis.wheelsArmor.get(wheelName, None)

    if matInfo is None:
        commonMaterialsInfo = vehicles.g_cache.commonConfig['materials']
        matInfo = commonMaterialsInfo.get(matKind)

    return matInfo


def _computePenetrationArmor(hitAngleCos, matInfo):
    # Returns the armor thickness that the shell should penetrate
    # Replicates the logic from the _getHitAngleCosWithNormalization() function in the cell/VehicleHarm.py
    armor = matInfo.armor

    if not matInfo.useHitAngle:
        return armor

    normalizationAngle = 0.0
    #shellExtraData = cls._SHELL_EXTRA_DATA[shell.kind]
    #if shellExtraData.hasNormalization:
    #    normalizationAngle = cls.__sessionProvider.arenaVisitor.modifiers.getShellNormalization(shell.kind)
    if normalizationAngle > 0.0 and hitAngleCos < 1.0:
        #if matInfo.checkCaliberForHitAngleNorm:
            #if shell.caliber > armor * 2 > 0:  # Apply the 2-caliber rule
            #    normalizationAngle *= 1.4 * shell.caliber / (armor * 2)  # from the task WOTD-11842

        hitAngle = math.acos(hitAngleCos) - normalizationAngle
        if hitAngle < 0.0:
            hitAngleCos = 1.0
        else:
            if hitAngle > math.pi / 2.0 - 1e-5:
                hitAngle = math.pi / 2.0 - 1e-5

            hitAngleCos = math.cos(hitAngle)

    if hitAngleCos < 1e-5:
        hitAngleCos = 1e-5

    return armor / hitAngleCos

g_ACService = ArmoryCheckerService()
