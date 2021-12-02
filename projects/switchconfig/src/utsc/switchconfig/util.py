from typing import (
    Any,
    Literal,
    Optional,
    Type,
    TypeAlias,
    ForwardRef,
    TYPE_CHECKING,
    Union,
    Mapping,
    get_origin,
    get_args,
)
import os
import sys
import string
import secrets
from pathlib import Path
from importlib.abc import Loader
from importlib.util import spec_from_file_location, spec_from_loader, module_from_spec

from . import config

from utsc.core import StrEnum, txt
from utsc.core.other import Prompt
from utsc.core.nested_data import NestedData
from pydantic import BaseModel, Field  # noqa
from pydantic.types import DirectoryPath
from loguru import logger  # noqa
from arrow import now
from jinja2 import Environment

if TYPE_CHECKING:
    from pydantic.fields import ModelField

    CommentBlockSchema: TypeAlias = Mapping[
        str, "CommentBlockField" | "CommentBlockSchema"
    ]

prompt = Prompt(config.util)


class SwitchConfigException(Exception):
    pass


class EnvVars:
    # a change to Jinja broke the ability to embed
    # os.environ as a simple dict into jinja environment's
    # globals. Here we wrap it in a simple getter
    def __getattr__(self, name):
        return os.environ.get(name, "")


# any object placed into this dictionary will be made available as a global variable in all templates
DEFAULT_GLOBALS = {
    "env_vars": EnvVars(),
    "now": now(),
    "password_gen": lambda: "".join(
        [secrets.choice(string.ascii_letters + string.digits) for i in range(24)]
    ),
}


class CommentBlockField(BaseModel):
    """
    A field from a comment block in a template.
    """

    name: str
    type: str
    desc: Optional[str] = None
    default: Optional[str] = None

    @property
    def base_name(self) -> str:
        return self.name.rpartition(".")[2]

    @property
    def type_(self) -> str:
        return self.type.rpartition(".")[2]


def get_comment_block_schema(template: str) -> Optional["CommentBlockSchema"]:
    comment_block = template.partition("{#")[2].partition("#}")[0].strip()
    if not comment_block:
        logger.debug("No comment block found in template")
        return None
    lines = comment_block.splitlines()
    first_line = lines[0]
    if first_line.startswith("#"):
        lines = lines[1:]
    lines = [line.strip() for line in lines if line]
    if not lines:
        logger.debug("Comment block in template appears to be empty")
        return None

    res = []
    for line in lines:
        line = map(lambda s: s.strip(), line.split("|", maxsplit=4))
        line = dict(enumerate(line))
        name = line[0]
        type_ = line[1]
        type_ = type_ or "str"
        try:
            # Use ForwardRef as a means to parse type definitions
            ForwardRef(type_)
        except SyntaxError as e:
            raise SwitchConfigException(
                f"Error parsing type {type_} for variable {name} in comment block: {e}"
            ) from e
        desc = line.get(2)
        desc = desc or None
        default = line.get(3)
        default = default or None
        field = CommentBlockField.construct(
            name=name, type=type_, desc=desc, default=default
        )
        res.append((name, field))
    res = NestedData.restructure(res)
    return res


def model_source_from_comment_block_schema(
    schema: "CommentBlockSchema", name="Model", import_list=None, render_imports=True
) -> str:
    import_list = import_list or ["typing.*", "pydantic.BaseModel, Field"]

    def field_value(field: CommentBlockField):
        # sourcery skip: remove-redundant-if
        if not field.default and not field.desc:
            return ""
        if field.default and not field.desc:
            return f"= {field.default}"
        if field.desc and not field.default:
            return f'= Field(description="{field.desc}")'
        return f'= Field({field.type_}("{field.default}"), description="{field.desc}")'

    def imports_src(import_list: list) -> str:
        res = ""
        for import_ in import_list:
            mod, _, type_ = import_.rpartition(".")
            res += f"from {mod} import {type_}\n"
        res += "\n\n"
        return res

    model_src = ""
    env = Environment(
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["field_value"] = field_value
    template = env.from_string(
        txt(
            """
            class {{name | capitalize}}(BaseModel):
                {% for field in fields %}
                {{field.base_name}}: {{field.type_}} {{field | field_value}}
                {% endfor +%}
            
            """
        )
    )
    fields = []
    for fname, field in schema.items():
        if isinstance(field, CommentBlockField):
            fields.append(field)
            if "." in field.type:
                import_list.append(field.type)
        else:
            model_src += model_source_from_comment_block_schema(
                field, fname, import_list, render_imports=False
            )
            fields.append(CommentBlockField(name=fname, type=fname.capitalize()))
    model_src += template.render(name=name, fields=fields)
    if render_imports:
        model_src = imports_src(import_list) + model_src
    return model_src


class VirtualSourceLoader(Loader):
    def __init__(self, source_code):
        self.source = source_code

    def create_module(self, spec):
        return None  # use default module creation semantics

    def exec_module(self, module) -> None:
        exec(self.source, module.__dict__)


def normalize_extension_name(extension_name: str):
    return extension_name.replace("-", "_").replace(".", "_").replace(" ", "_")


def create_python_module(module_name, source: Path | str):
    if isinstance(source, Path):
        spec = spec_from_file_location(module_name, source)
    else:
        spec = spec_from_loader(module_name, VirtualSourceLoader(source))
    assert spec is not None
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return sys.modules[module_name]


def construct_model_from_comment_block_schema(
    schema: "CommentBlockSchema", name="Model"
) -> Type[BaseModel]:
    """
    Given a list of CommentBlockFields, construct a pydantic model
    that corresponds to the fields in the comment block.
    """
    model_src = model_source_from_comment_block_schema(schema, name)
    module_name = f"<virtual_module#{hash(model_src)}>"
    module = create_python_module(module_name, model_src)
    return getattr(module, name)


class Choice(BaseModel):
    # Base class used to define multiple choices in a discriminated union.
    # see the "Union" example under https://pydantic-docs.helpmanual.io/usage/types/#literal-type
    # for details
    kind: str


def discriminated_union_choices(field: "ModelField") -> dict[str, Type] | None:
    """
    Return the set of kind literals for a discriminated union,
    or None if this field is not a discriminated union.

    Given a pydantic model field whose annotation is something like `Union[Choice1,Choice2,Choice3],
    and given that each of these sub types of the union is an instance of Choice,
    and given that each of these Choice subclasses has a `kind` attribute annotated with a Literal string,
    return the set of strings of all choices"""
    if get_origin(field.type_) is not Union:  # type: ignore
        return None
    assert isinstance(field.sub_fields, list)
    choices = {}
    for sub in field.sub_fields:
        if not issubclass(sub.type_, Choice):
            return None
        kind_type = sub.type_.__fields__["kind"].type_
        assert get_origin(kind_type) is Literal
        choice = get_args(kind_type)[0]
        choices[choice] = sub.type_
    return choices


ValidatorBase = prompt.Validator


class ValidatorWrapper(ValidatorBase):
    def __init__(self, field: "ModelField", values: dict[str, Any]) -> None:
        self.field = field
        self.values = values

    def validate(self, document) -> None:
        _, errors = self.field.validate(document.text, self.values, loc=self.field.name)
        if errors:
            from pydantic.error_wrappers import ErrorWrapper  # noqa

            if isinstance(errors, ErrorWrapper):
                raise prompt.ValidationError(message=str(errors.exc))
            # else:
            raise prompt.ValidationError(message=str(errors))


def model_questionnaire(
    model: Type["BaseModel"], input_data: dict[str, Any] | None = None
):
    """
    Given a pydantic data model,
    prompt user for inputs matching fields on that model,
    and return an instance of that model
    """
    assert issubclass(model, BaseModel)

    def _is_maybe_subclass(type_, class_):
        try:
            return issubclass(type_, class_)
        except TypeError:
            return False

    input_data = input_data or {}
    for name, field in model.__fields__.items():
        if name in input_data:
            continue

        desc = field.field_info.description
        default = field.default

        if (field.required is False) and (
            prompt.bool_(f"include {name}?", desc) is False
        ):
            continue
        if choices := discriminated_union_choices(field):
            choice = prompt.select(name, list(choices.keys()), desc)
            input_data[name] = model_questionnaire(choices[choice], {"kind": choice})
            continue
        elif _is_maybe_subclass(field.type_, StrEnum):
            choices = list(field.type_.__members__.keys())
            input_data[name] = prompt.select(name, choices, desc)
            continue
        elif get_origin(field.type_) is Literal:
            choices = list(get_args(field.type_))
            input_data[name] = prompt.select(name, choices, desc)
            continue
        elif _is_maybe_subclass(field.type_, BaseModel):
            input_data[name] = model_questionnaire(field.type_)
            continue
        elif _is_maybe_subclass(field.type_, Path):
            only_directories = issubclass(field.type_, DirectoryPath)
            input_data[name] = prompt.path(
                name, desc, only_directories=only_directories
            )
            continue
        if field.key_field:
            # only dict[str,str] supported for now
            input_data[name] = prompt.dict_(name, desc)
        # TODO: add handlers for fields of type list[str] etc.
        else:
            # prompt for str, and let pydantic's validators sort it out
            validator = ValidatorWrapper(field, input_data)

            input_data[name] = prompt.string(name, desc, default, validator=validator)
    return input_data
