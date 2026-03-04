import enum


class AssetStatus(str, enum.Enum):
    DRAFT = "draft"
    REGISTERED = "registered"
    SHARED = "shared"
    ARCHIVED = "archived"


ASSET_STATUS_TRANSITIONS = {
    AssetStatus.DRAFT: {AssetStatus.REGISTERED},
    AssetStatus.REGISTERED: {AssetStatus.SHARED, AssetStatus.ARCHIVED},
    AssetStatus.SHARED: {AssetStatus.ARCHIVED},
    AssetStatus.ARCHIVED: set(),
}


class VersionStage(str, enum.Enum):
    DRAFT = "draft"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


VERSION_STAGE_TRANSITIONS = {
    VersionStage.DRAFT: {VersionStage.DEVELOPMENT, VersionStage.ARCHIVED},
    VersionStage.DEVELOPMENT: {VersionStage.STAGING, VersionStage.ARCHIVED},
    VersionStage.STAGING: {
        VersionStage.PRODUCTION, VersionStage.DEVELOPMENT, VersionStage.ARCHIVED,
    },
    VersionStage.PRODUCTION: {VersionStage.ARCHIVED},
    VersionStage.ARCHIVED: set(),
}


class DeploymentStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
