from datetime import datetime
from queue import Empty
from typing import Optional, List
from pydantic import BaseModel, root_validator

# from pylon.core.tools import log
from tools import rpc_tools

from .base import AuthorBaseModel
from .list import PromptListModel
from .detail import PromptTagDetailModel
from ..enums.all import CollectionPatchOperations


class PromptIds(BaseModel):
    id: int
    owner_id: int


class CollectionPatchModel(BaseModel):
    operation: CollectionPatchOperations
    prompt: PromptIds


class CollectionModel(BaseModel):
    name: str
    owner_id: int
    author_id: Optional[int]
    description: Optional[str]
    prompts: Optional[List[PromptIds]] = []
    shared_id: Optional[int]
    shared_owner_id: Optional[int]


class PromptBaseModel(BaseModel):
    id: int
    name: str
    description: Optional[str]
    owner_id: int

    class Config:
        orm_mode = True


class CollectionDetailModel(BaseModel):
    id: int
    name: str
    description: Optional[str]
    owner_id: int
    status: str
    author_id: int
    prompts: Optional[List[PromptListModel]] = []
    author: Optional[AuthorBaseModel]
    created_at: datetime

    class Config:
        orm_mode = True


class CollectionUpdateModel(BaseModel):
    name: Optional[str]
    description: Optional[str]
    owner_id: Optional[int]
    status: str
    prompts: Optional[List[PromptIds]] = {}


class CollectionListModel(BaseModel):
    id: int
    name: str
    description: Optional[str]
    owner_id: int
    author_id: int
    status: str
    author: Optional[AuthorBaseModel]
    prompts: Optional[List] = []
    tags: List[PromptTagDetailModel] = []
    created_at: datetime
    includes_prompt: Optional[bool] = None
    prompt_count: int = 0

    class Config:
        orm_mode = True
        fields = {
            "prompts": {"exclude": True},
        }

    @root_validator
    def count_prompts(cls, values):
        count = len(values.get("prompts"))
        values["prompt_count"] = count
        return values


class PublishedCollectionListModel(CollectionListModel):
    likes: Optional[int]
    is_liked: Optional[bool]


class PublishedCollectionDetailModel(CollectionDetailModel):
    likes: Optional[int]
    is_liked: Optional[bool]


    def get_likes(self, project_id: int) -> None:
        try:
            likes_data = rpc_tools.RpcMixin().rpc.timeout(2).social_get_likes(
                project_id=project_id, entity='collection', entity_id=self.id
            )
            # self.likes = [LikeModel(**like) for like in likes_data['rows']]
            self.likes = likes_data['total']
        except Empty:
            self.likes = 0

    def check_is_liked(self, project_id: int) -> None:
        try:
            self.is_liked = rpc_tools.RpcMixin().rpc.timeout(2).social_is_liked(
                project_id=project_id, entity='collection', entity_id=self.id
            )
        except Empty:
            self.is_liked = False
