"""SQLAlchemy domain model exports."""

from app.models import (
    audience,
    campaign,
    document,
    entity,
    event,
    fact,
    relationship,
    user,
)
from app.models.audience import EntityFactAudience, EntityRelationshipFactAudience
from app.models.campaign import Campaign, CampaignMember, Session
from app.models.document import Document, DocumentStatement
from app.models.entity import (
    Actor,
    Entity,
    EntityAlias,
    Faction,
    Item,
    Location,
    Player,
    PlayerCharacter,
)
from app.models.event import Event
from app.models.fact import EntityFact, EntityRelationshipFact
from app.models.relationship import EntityRelationship
from app.models.user import User

__all__ = [
    "Actor",
    "Campaign",
    "CampaignMember",
    "Document",
    "DocumentStatement",
    "Entity",
    "EntityAlias",
    "EntityFact",
    "EntityFactAudience",
    "EntityRelationship",
    "EntityRelationshipFact",
    "EntityRelationshipFactAudience",
    "Event",
    "Faction",
    "Item",
    "Location",
    "Player",
    "PlayerCharacter",
    "Session",
    "User",
]

# Remove module references from namespace
del audience, campaign, document, entity, event, fact, relationship, user