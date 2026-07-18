from enum import StrEnum


class PartyRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class EventCreationPolicy(StrEnum):
    EVERYONE = "everyone"
    ADMINS_ONLY = "admins_only"


class EventType(StrEnum):
    SMOKE = "smoke"
    COFFEE = "coffee"
    LUNCH = "lunch"
    AFTER_WORK = "after_work"
    CUSTOM = "custom"

    @property
    def emoji(self) -> str:
        return {
            self.SMOKE: "🚬",
            self.COFFEE: "☕",
            self.LUNCH: "🍔",
            self.AFTER_WORK: "🍺",
            self.CUSTOM: "🎮",
        }[self]

    @property
    def default_title(self) -> str:
        return {
            self.SMOKE: "Го курить",
            self.COFFEE: "Го кофе",
            self.LUNCH: "Го обедать",
            self.AFTER_WORK: "После работы",
            self.CUSTOM: "Другой движ",
        }[self]


class EventStatus(StrEnum):
    ACTIVE = "active"
    STARTED = "started"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ResponseType(StrEnum):
    GOING = "going"
    LATER = "later"
    DECLINED = "declined"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"
