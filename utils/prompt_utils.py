from json import loads
import json
from typing import List
from sqlalchemy import func, cast, String
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

from tools import db
from pylon.core.tools import log

from ..models.all import PromptVariable
from ..models.pd.legacy.variable import VariableModel
from ..models.pd.update import PromptVersionUpdateModel
from ..models.pd.detail import PromptVersionDetailModel
from ..models.all import Prompt, PromptVersion, PromptVariable, PromptMessage, PromptTag, PromptVersionTagAssociation


def create_variables_bulk(project_id: int, variables: List[dict], **kwargs) -> List[dict]:
    result = []
    with db.with_project_schema_session(project_id) as session:
        for i in variables:
            variable_data = VariableModel.parse_obj(i)
            variable = PromptVariable(
                prompt_version_id=variable_data.prompt_id,
                name=variable_data.name,
                value=variable_data.value
            )
            result.append(variable)
            session.add(variable)
        session.commit()
        return [i.to_json() for i in result]


def prompts_create_variable(project_id: int, variable: dict, **kwargs) -> dict:
    return create_variables_bulk(project_id, [variable])[0]


def get_prompt_tags(project_id: int, prompt_id: int) -> List[dict]:
    with db.with_project_schema_session(project_id) as session:
        query = (
            session.query(PromptTag)
            .join(PromptVersionTagAssociation, PromptVersionTagAssociation.c.tag_id == PromptTag.id)
            .join(PromptVersion, PromptVersion.id == PromptVersionTagAssociation.c.version_id)
            .filter(PromptVersion.prompt_id == prompt_id)
            .order_by(PromptVersion.id)
        )
        return [tag.to_json() for tag in query.all()]


def get_all_ranked_tags(project_id: int, top_n: int=20) -> List[dict]:
    with db.with_project_schema_session(project_id) as session:
        query = (
            session.query(
                PromptTag.id,
                PromptTag.name,
                cast(PromptTag.data, String),
                func.count(func.distinct(PromptVersion.prompt_id))
            )
            .join(PromptVersionTagAssociation, PromptVersionTagAssociation.c.tag_id == PromptTag.id)
            .join(PromptVersion, PromptVersion.id == PromptVersionTagAssociation.c.version_id)
            .group_by(PromptTag.id, PromptTag.name, cast(PromptTag.data, String))
            .order_by(func.count(func.distinct(PromptVersion.prompt_id)).desc())
            .limit(top_n)
        )
        as_dict = lambda x: {'id': x[0], 'name': x[1], 'data': loads(x[2]), 'prompt_count': x[3]}
        return [as_dict(tag) for tag in query.all()]


def _update_related_table(session, version, version_data, db_model):
    added_ids = set()
    existing_entities = session.query(db_model).filter(
        db_model.id.in_({i.id for i in version_data if i.id})
    ).all()
    existing_entities_map = {i.id: i for i in existing_entities}

    for pd_model in version_data:
        if pd_model.id in existing_entities_map:
            entity = existing_entities_map[pd_model.id]
            for key, value in pd_model.dict(exclude={'id'}).items():
                setattr(entity, key, value)
        else:
            entity = db_model(**pd_model.dict())
            entity.prompt_version = version
            log.info(f'{entity=}')
            session.add(entity)
        session.flush()
        added_ids.add(entity.id)

    usused_entities = session.query(db_model).filter(
        db_model.prompt_version_id == version.id,
        db_model.id.not_in(added_ids)
    ).all()
    for entity in usused_entities:
        session.delete(entity)


def prompts_update_version(project_id: int, version_data: PromptVersionUpdateModel) -> List[dict]:
    with db.with_project_schema_session(project_id) as session:
        version = session.query(PromptVersion).filter(
            PromptVersion.id == version_data.id
        ).first()
        if not version:
            return {'updated': False, 'msg': f'Prompt version with id {version_data.id} not found'}

        for key, value in version_data.dict(exclude={'variables', 'messages', 'tags'}).items():
            setattr(version, key, value)
        try:
            _update_related_table(session, version, version_data.variables, PromptVariable)
            _update_related_table(session, version, version_data.messages, PromptMessage)

            version.tags.clear()
            existing_tags = session.query(PromptTag).filter(
                PromptTag.name.in_({i.name for i in version_data.tags})
            ).all()
            existing_tags_map = {i.name: i for i in existing_tags}
            for tag in version_data.tags:
                prompt_tag = existing_tags_map.get(tag.name, PromptTag(**tag.dict()))
                version.tags.append(prompt_tag)

            session.add(version)
            session.commit()
        except IntegrityError:
            return {'updated': False, 'msg': 'Values you passed violates unique constraint'}

        result = PromptVersionDetailModel.from_orm(version)
        return {'updated': True, 'data': json.loads(result.json())}
