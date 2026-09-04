import enum


class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    PROVIDER = "PROVIDER"
    SUPPORT = "SUPPORT"
    ADMIN = "ADMIN"


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"


class VehicleFuelType(str, enum.Enum):
    PETROL = "PETROL"
    DIESEL = "DIESEL"
    CNG = "CNG"
    EV = "EV"
    HYBRID = "HYBRID"
    OTHER = "OTHER"


class ServiceCategory(str, enum.Enum):
    TOWING = "TOWING"
    BATTERY = "BATTERY"
    TYRE = "TYRE"
    FUEL = "FUEL"
    MECHANICAL = "MECHANICAL"
    GENERAL = "GENERAL"
    SERVICE = "SERVICE"


class ProviderType(str, enum.Enum):
    MECHANIC = "MECHANIC"
    GARAGE = "GARAGE"
    TOWING = "TOWING"
    BATTERY = "BATTERY"
    TYRE = "TYRE"
    OTHER = "OTHER"


class ProviderVerificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REJECTED = "REJECTED"


class ProviderDocumentType(str, enum.Enum):
    IDENTITY = "IDENTITY"
    ADDRESS = "ADDRESS"
    BUSINESS = "BUSINESS"
    LICENSE = "LICENSE"
    OTHER = "OTHER"


class ProviderDocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class BookingType(str, enum.Enum):
    EMERGENCY = "EMERGENCY"
    SCHEDULED = "SCHEDULED"


class BookingStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    SEARCHING = "SEARCHING"
    PROVIDER_ASSIGNED = "PROVIDER_ASSIGNED"
    ACCEPTED = "ACCEPTED"
    ON_THE_WAY = "ON_THE_WAY"
    ARRIVED = "ARRIVED"
    INSPECTION = "INSPECTION"
    ESTIMATE_PENDING = "ESTIMATE_PENDING"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    INVOICE_GENERATED = "INVOICE_GENERATED"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


class LocationType(str, enum.Enum):
    PICKUP = "PICKUP"
    SERVICE = "SERVICE"
    DESTINATION = "DESTINATION"


class AuditAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    STATUS_CHANGE = "STATUS_CHANGE"
    LOGIN = "LOGIN"
    ASSIGN = "ASSIGN"
