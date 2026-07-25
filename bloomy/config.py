import inspect
import io
import typing
from pathlib import Path
from types import UnionType
from typing import NamedTuple, Any, Self

import ruamel.yaml

_yaml = ruamel.yaml.YAML()
__all__ = [
    "DictConfig",
    "DictConfigFile",
    "DictConfigFileYaml",
    "Field",
]


class DictConfigFile:
    def load_file(self, config: "DictConfig", fields: dict[str, Any], *, create_default_file=True):
        raise NotImplementedError

    def save_file(self, config: "DictConfig", fields: dict[str, Any], *, ignore_no_set=True):
        raise NotImplementedError


class DictConfigFileYaml(DictConfigFile):
    yaml = _yaml

    def __init__(self, path: str | Path):
        self.path = path
        self._data = {}

    def load_file(self, config: "DictConfig", fields: dict[str, Any], *, create_default_file=True):
        if self.path.is_file():
            with self.path.open("r", encoding="utf-8") as f:
                self._data = self.yaml.load(f) or {}  # type: dict
            _save_file = False
        else:
            self._data = {}
            _save_file = True

        _invalid_values = set()
        _new_data = dict()

        for key, field in fields.items():
            try:
                value = field.check_value_type(self._data[key])
            except KeyError:
                if field.required:
                    _invalid_values.add(key)
                value = field.default
                _save_file = True
            except TypeError:
                _invalid_values.add(key)
                continue

            _new_data[key] = value

        config.clear()
        config.update(_new_data)

        if _save_file and create_default_file:
            self.save_file(config, fields)

        if _invalid_values:
            raise KeyError("Invalid configuration values: " + ", ".join(_invalid_values))

    def save_file(self, config: "DictConfig", fields: dict[str, Any], *, ignore_no_set=True):
        self.path.parent.mkdir(parents=True, exist_ok=True)

        for key, field in fields.items():
            try:
                value = config[key]
            except KeyError:
                if field.required:
                    if not ignore_no_set:
                        raise
                value = field.default
            self._data[key] = value

        with io.StringIO() as temp:
            self.yaml.dump(self._data, temp)
            temp.seek(0)

            with self.path.open("w", encoding="utf-8") as file:
                file.write(temp.read())


class Field(NamedTuple):
    name: str
    annotation: Any
    required: bool
    default: Any | None

    @classmethod
    def get_fields(cls, config_cls):
        fields = {}  # type: dict[str, Field]
        for name, anno in inspect.get_annotations(config_cls).items():

            if typing.get_origin(anno) is UnionType:
                disallow_types = set(typing.get_args(anno))
            else:
                disallow_types = {anno}

            # for _allow in (str, bool, float, int, type(None), None, DictConfig):
            for _allow in (str, bool, float, int, type(None), None):
                disallow_types.discard(_allow)

            # for _type in list(disallow_types):
            #     if issubclass(_type, DictConfig):
            #         disallow_types.discard(_type)

            if disallow_types:
                raise TypeError("Unsupported types: " + ", ".join(map(str, disallow_types)) + f" in {name!r}")

            default = getattr(config_cls, name, None)
            required = not (isinstance(None, anno) or hasattr(config_cls, name))
            fields[name] = cls(name, anno, required, default)
        return fields

    def check_value_type(self, value: Any):
        if value is None:
            if self.required:
                raise TypeError(f"Value {self.name!r} is not optional")
            value = self.default

        if not isinstance(value, self.annotation):
            raise TypeError(f"Expected {self.annotation} by {self.name!r}")

        return value


class DictConfig(dict):
    """
    型アノテーションによる型チェックとデフォルト値を適用できるシンプルなConfigurationクラス
    現在は str, bool, float, int, None のみ対応 (ネスト未実装 ※現在は)

    # Example
    class MyConfig(DictConfig):
        type: str
        display: str | None  # optional
        super: bool = True  # optional with default=True


    config = MyConfig.create_yaml("myconf.yml")
    config.load_file()

    print("type:", config.type)
    print("display:", config.display)
    print("is super:", config.super)
    ```

    """

    @classmethod
    def create_yaml(cls, file_path: str | Path) -> Self:
        return cls(file_driver=DictConfigFileYaml(file_path))

    def __init__(self, defaults: dict = None, *, file_driver: DictConfigFile | None):
        super().__init__()
        self._file_driver = file_driver
        self._fields = Field.get_fields(type(self))

        if defaults is not None:
            self.update(defaults)

    def load_file(self, *, create_default_file=True):
        if not self._file_driver:
            raise ValueError("No config file driver")
        return self._file_driver.load_file(self, self._fields, create_default_file=create_default_file)

    def save_file(self):
        if not self._file_driver:
            raise ValueError("No config file driver")

        self._file_driver.save_file(self, self._fields)

    def __getattribute__(self, item):
        try:
            fields = super().__getattribute__("_fields")  # type: dict[str, Field]
        except AttributeError:
            return super().__getattribute__(item)

        try:
            field = fields[item]
        except KeyError:
            try:
                return super().__getattribute__(item)
            except AttributeError:
                raise AttributeError(f"Unknown config key: {item!r}") from None

        return field.check_value_type(self.get(field.name, field.default))

    def __setattr__(self, key, value):
        try:
            fields = super().__getattribute__("_fields")
        except AttributeError:
            return super().__setattr__(key, value)

        try:
            field = fields[key]
        except KeyError:
            raise AttributeError(f"Unknown config key: {key!r}")

        self[key] = field.check_value_type(value)
