import math

import BigWorld
import Math
import GUI
from CurrentVehicle import g_currentPreviewVehicle
from Vehicle import SegmentCollisionResultExt
from gui.shared.utils.functions import makeTooltip
from gui.shared.utils.scheduled_notifications import Notifiable, PeriodicNotifier

from helpers import dependency
from items import vehicles
from skeletons.gui.app_loader import IAppLoader
from skeletons.gui.shared.utils import IHangarSpace
from vehicle_systems.model_assembler import collisionIdxToTrackPairIdx
from vehicle_systems.tankStructure import TankPartIndexes


class ArmoryCheckerService(object):

    # dependency injection
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
        """
        Ищем коллизии с танком
        """

        # курсор на экране, в фокусе и над 3д сценой
        cursorPosition = GUI.mcursor().position if (GUI.mcursor().inWindow and GUI.mcursor().inFocus and
                                                    self.__hangarSpace.isCursorOver3DScene) else None

        if self.__currentCursorPos != cursorPosition:
            self.__currentCollisions = []
            ray, wpoint = _getWorldRayAndPoint(cursorPosition.x, cursorPosition.y)
            vehicle = BigWorld.entities[g_currentPreviewVehicle.vehicleEntityID]
            if vehicle.appearance.collisions is not None:
                # collideAllWorld does the collision test with an attachment in the world space
                # returns all collisions (dist, rayAngleCos, matkind, partIndex)
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


def getMatinfo(entity, partIndex, matKind):
    """
    :param entity:  vehicle entity
    :param parIndex: Vehicle part index
    :param matKind: id material
    :return:
    """
    matInfo = None

    if partIndex == TankPartIndexes.CHASSIS:
        matInfo = entity.typeDescriptor.chassis.materials.get(matKind)
    elif partIndex == TankPartIndexes.HULL:
        matInfo = entity.typeDescriptor.hull.materials.get(matKind)
    elif partIndex == TankPartIndexes.TURRET:
        matInfo = entity.typeDescriptor.turret.materials.get(matKind)
    elif partIndex == TankPartIndexes.GUN:
        matInfo = entity.typeDescriptor.gun.materials.get(matKind)
    elif partIndex > len(TankPartIndexes.ALL):
        trackPairIdx = collisionIdxToTrackPairIdx(partIndex, entity.typeDescriptor)
        if trackPairIdx is not None:
            matInfo = entity.typeDescriptor.chassis.tracks[trackPairIdx].materials.get(matKind)
    elif entity.typeDescriptor.type.isWheeledVehicle and entity.appearance.collisions is not None:
        wheelName = entity.appearance.collisions.getPartName(partIndex)
        if wheelName is not None:
            matInfo = entity.typeDescriptor.chassis.wheelsArmor.get(wheelName, None)

    if matInfo is None:
        commonMaterialsInfo = vehicles.g_cache.commonConfig['materials']
        matInfo = commonMaterialsInfo.get(matKind)

    return matInfo


def _computePenetrationArmor(hitAngleCos, matInfo):
    """
    Calculate penetration armor
    :param hitAngleCos: cosinus betwen ray(hit) and armor
    :param matInfo: Material info structure
    :return: penetration armor
    """
    armor = matInfo.armor

    if not matInfo.useHitAngle:
        return armor

    if hitAngleCos < 1e-5:
        hitAngleCos = 1e-5

    return armor / hitAngleCos


def _getWorldRayAndPoint(x, y):
    """
    Get world ray and point on near plane of camera
    """
    fov = BigWorld.projection().fov  # Field of view (angle in rad)
    near = BigWorld.projection().nearPlane  # Distance from camera to near plane
    aspect = BigWorld.getAspectRatio()
    yLength = near * math.tan(fov * 0.5)
    xLength = yLength * aspect

    # point on near plane
    point = Math.Vector3(xLength * x, yLength * y, near)

    inv = Math.Matrix(BigWorld.camera().invViewMatrix)
    ray = inv.applyVector(point)
    wPoint = inv.applyPoint(point)
    return ray, wPoint


g_ACService = ArmoryCheckerService()
