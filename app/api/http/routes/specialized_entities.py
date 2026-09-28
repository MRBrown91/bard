"""Specialized entity API endpoints.

Each of the six types gets the same five endpoints over the same use cases, so
the routes are built from one factory rather than written out six times. What
differs between types — path, tag, schemas, repository dependency — is passed
in as arguments.

The specialization shares the entity's UUID, so ``{id}`` is the same
identifier in ``/entities/{id}`` and ``/actors/{id}``.
"""

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from pydantic import BaseModel

from app.api.dependencies import (
    CurrentCampaign,
    get_actor_repo,
    get_faction_repo,
    get_item_repo,
    get_location_repo,
    get_player_character_repo,
    get_player_repo,
)
from app.application.entities.specialized import (
    count_specialized,
    create_specialized,
    get_specialized,
    list_specialized,
    soft_delete_specialized,
    update_specialized,
)
from app.models import Entity
from app.schemas.specialized import (
    ActorCreate,
    ActorRead,
    ActorUpdate,
    FactionCreate,
    FactionRead,
    FactionUpdate,
    ItemCreate,
    ItemRead,
    ItemUpdate,
    LocationCreate,
    LocationRead,
    LocationUpdate,
    PlayerCharacterCreate,
    PlayerCharacterRead,
    PlayerCharacterUpdate,
    PlayerCreate,
    PlayerRead,
    PlayerUpdate,
    SpecializedList,
)


def build_read_model[T: BaseModel](
    entity: Entity, specialized: Any, read_model: type[T]
) -> T:
    """Build a specialized read model from the entity and row pair.

    Composed explicitly because the pair is a tuple rather than an object with
    the layout the schema expects. Every field the read model declares is taken
    from the specialized row except ``entity``, which comes from the parent.
    """
    payload: dict[str, Any] = {
        name: getattr(specialized, name)
        for name in read_model.model_fields
        if name != "entity" and hasattr(specialized, name)
    }
    return read_model.model_validate({**payload, "entity": entity})


def build_specialized_router[T: BaseModel](
    *,
    path: str,
    tag: str,
    create_model: type[BaseModel],
    read_model: type[T],
    update_model: type[BaseModel],
    repo_dependency: Callable[..., Any],
) -> APIRouter:
    """Build the five CRUD routes for one specialized entity type."""
    sub = APIRouter(prefix=f"/api/campaigns/{{campaign_id}}/{path}", tags=[tag])
    repo_dep = Annotated[Any, Depends(repo_dependency)]
    entity_id_path = Annotated[
        UUID, Path(description="Entity id, shared with the entity")
    ]

    @sub.post("", response_model=read_model, status_code=status.HTTP_201_CREATED)
    async def create_specialized_endpoint(
        data: create_model,  # type: ignore[valid-type]
        campaign: CurrentCampaign,
        repo: repo_dep,
    ) -> T:
        """Attach this specialization to an existing entity of the matching type.

        The entity is created first through /entities, so this endpoint never
        has to insert an entity and its specialization in a dependent order.
        """
        entity, specialized = await create_specialized(data, repo)
        return build_read_model(entity, specialized, read_model)

    @sub.get("", response_model=SpecializedList[read_model])  # type: ignore[valid-type]
    async def list_specialized_endpoint(
        campaign: CurrentCampaign,
        repo: repo_dep,
        name_contains: Annotated[str | None, Query(max_length=255)] = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> SpecializedList[Any]:
        """List this campaign's specializations, newest first."""
        total = await count_specialized(repo, name_contains=name_contains)
        pairs = await list_specialized(
            repo,
            name_contains=name_contains,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return SpecializedList(
            items=[build_read_model(e, s, read_model) for e, s in pairs],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=-(-total // page_size),
        )

    @sub.get("/{id}", response_model=read_model)
    async def get_specialized_endpoint(
        campaign: CurrentCampaign,
        repo: repo_dep,
        id: entity_id_path,
    ) -> T:
        """Get one specialization with its base entity."""
        entity, specialized = await get_specialized(id, repo)
        return build_read_model(entity, specialized, read_model)

    @sub.patch("/{id}", response_model=read_model)
    async def update_specialized_endpoint(
        data: update_model,  # type: ignore[valid-type]
        campaign: CurrentCampaign,
        repo: repo_dep,
        id: entity_id_path,
    ) -> T:
        """Update specialization fields. The base entity is not modified."""
        entity, specialized = await update_specialized(id, data, repo)
        return build_read_model(entity, specialized, read_model)

    @sub.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_specialized_endpoint(
        campaign: CurrentCampaign,
        repo: repo_dep,
        id: entity_id_path,
    ) -> None:
        """Soft delete the specialization, keeping the entity intact."""
        await soft_delete_specialized(id, repo)

    return sub


routers = [
    build_specialized_router(
        path="actors",
        tag="actors",
        create_model=ActorCreate,
        read_model=ActorRead,
        update_model=ActorUpdate,
        repo_dependency=get_actor_repo,
    ),
    build_specialized_router(
        path="players",
        tag="players",
        create_model=PlayerCreate,
        read_model=PlayerRead,
        update_model=PlayerUpdate,
        repo_dependency=get_player_repo,
    ),
    build_specialized_router(
        path="player-characters",
        tag="player-characters",
        create_model=PlayerCharacterCreate,
        read_model=PlayerCharacterRead,
        update_model=PlayerCharacterUpdate,
        repo_dependency=get_player_character_repo,
    ),
    build_specialized_router(
        path="locations",
        tag="locations",
        create_model=LocationCreate,
        read_model=LocationRead,
        update_model=LocationUpdate,
        repo_dependency=get_location_repo,
    ),
    build_specialized_router(
        path="items",
        tag="items",
        create_model=ItemCreate,
        read_model=ItemRead,
        update_model=ItemUpdate,
        repo_dependency=get_item_repo,
    ),
    build_specialized_router(
        path="factions",
        tag="factions",
        create_model=FactionCreate,
        read_model=FactionRead,
        update_model=FactionUpdate,
        repo_dependency=get_faction_repo,
    ),
]
