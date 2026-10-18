"""Compatibilidad de imports del refactor núcleo/perfiles: cada nombre viejo es el MISMO módulo que el nuevo
(así los monkeypatch de los tests llegan al núcleo y las clases no se duplican). Sin red ni Mongo."""
import importlib
import sys
import warnings

import pytest

from assistant import _compat


def test_alias_es_el_mismo_modulo_con_su_spec_y_avisa(monkeypatch):
    # destino que nunca se mueve (los módulos movidos ya son alias a su vez)
    monkeypatch.setitem(_compat.ALIASES, "assistant._probe", "assistant.core")
    real = importlib.import_module("assistant.core")
    spec, package = real.__spec__, real.__package__
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            probe = importlib.import_module("assistant._probe")
        assert probe is real
        assert real.__spec__ is spec and real.__spec__.name == "assistant.core" and real.__package__ == package
        assert [w.category for w in caught] == [DeprecationWarning]
        importlib.reload(real)  # el spec restaurado permite recargar
    finally:
        sys.modules.pop("assistant._probe", None)


def test_cada_nombre_viejo_es_el_modulo_nuevo():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for old, new in _compat.ALIASES.items():
            assert importlib.import_module(old) is importlib.import_module(new), old
            assert importlib.import_module(new).__spec__.name == new, new
        # submódulos ya importados por su nombre viejo (p. ej. assistant.appdata.mongo)
        for name in [n for n in list(sys.modules) if _compat.resolve(n) and n not in _compat.ALIASES]:
            assert sys.modules[name] is importlib.import_module(_compat.resolve(name)), name


def test_nombre_fuera_del_mapa_no_se_intercepta():
    assert _compat.resolve("assistant.no_existe") is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("assistant.no_existe")
