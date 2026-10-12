import pytest
from functions_helpers import DESC
from pydantic import ValidationError

from app.functions.spec import (
    AppSpec, AuthSpec, AuthType, ConfirmationPolicy, ErrorCode, ErrorInfo, Example,
    FunctionSpec, Result, Status, Verb,
)


def make_spec(**over) -> FunctionSpec:
    base = dict(
        id="dropbox.files.list", version=1, app="dropbox", verb=Verb.read,
        description=DESC,
        examples=[Example(input={"path": ""})],
        input_schema={"type": "object"}, output_schema={"type": "object"},
    )
    base.update(over)
    return FunctionSpec(**base)


@pytest.mark.parametrize("bad", ["dropbox", "dropbox.files", "Dropbox.files.list", "dropbox.files.list.more", "1x.files.list", "dropbox..list"])
def test_id_must_be_app_resource_verb(bad):
    with pytest.raises(ValidationError):
        make_spec(id=bad)


def test_id_must_start_with_app():
    with pytest.raises(ValidationError):
        make_spec(id="brevo.files.list")


def test_needs_at_least_one_example_and_version_ge_1():
    with pytest.raises(ValidationError):
        make_spec(examples=[])
    with pytest.raises(ValidationError):
        make_spec(version=0)


def test_read_cannot_exit_outside():
    with pytest.raises(ValidationError):
        make_spec(exits_outside=True)


@pytest.mark.parametrize("verb,exits,rev,expected", [
    (Verb.read, False, True, ConfirmationPolicy.assume),
    (Verb.create, False, True, ConfirmationPolicy.assume),
    (Verb.update, False, True, ConfirmationPolicy.assume),
    (Verb.create, True, True, ConfirmationPolicy.draft_and_confirm),   # enviar correo
    (Verb.update, False, False, ConfirmationPolicy.ask),                # irreversible
    (Verb.delete, False, True, ConfirmationPolicy.ask),                 # eliminar siempre pregunta
    (Verb.delete, True, False, ConfirmationPolicy.ask),                 # lo irreversible gana a "sale al exterior"
])
def test_confirmation_policy_is_derived(verb, exits, rev, expected):
    s = make_spec(id="dropbox.files.do", verb=verb, exits_outside=exits, reversible=rev)
    assert s.confirmation_policy == expected


def test_spec_hash_is_the_contract_hash_and_ignores_status_and_wording():
    a, b = make_spec(), make_spec()
    assert a.spec_hash == b.spec_hash
    assert make_spec(status=Status.active).spec_hash == a.spec_hash                      # el status se cambia en Mongo sin desplegar
    assert make_spec(description=DESC + " Better wording.").spec_hash == a.spec_hash     # mejorar el texto no rompe a nadie
    assert make_spec(examples=[Example(input={"path": "/otro"})]).spec_hash == a.spec_hash
    docs = {"type": "object", "title": "T", "properties": {"q": {"type": "string", "description": "text one"}}}
    docs2 = {"type": "object", "title": "OTRO", "properties": {"q": {"type": "string", "description": "completely different words"}}}
    assert make_spec(input_schema=docs).spec_hash == make_spec(input_schema=docs2).spec_hash   # description/title de los esquemas no cuentan
    for breaking in (dict(version=2), dict(verb=Verb.update), dict(reversible=False), dict(scopes=["x"]), dict(upstream_api="v9"),
                     dict(input_schema={"type": "object", "properties": {"q": {"type": "integer"}}})):   # un cambio de tipo si
        assert make_spec(**breaking).spec_hash != a.spec_hash, breaking


def test_description_must_be_complete():
    make_spec(description="x" * 0 + DESC)
    with pytest.raises(ValidationError, match="completa"):
        make_spec(description="Lists files.")
    with pytest.raises(ValidationError, match="completa"):
        make_spec(description="word " * 39)  # 195 caracteres: justo por debajo del minimo


def test_description_must_be_english():
    spanish_accents = ("Devuelve la cuenta conectada del usuario. " * 8)
    spanish_plain = ("Lista los archivos de una carpeta para el usuario con su nombre y su ruta completa. " * 4)
    for text in (spanish_accents, spanish_plain):
        assert len(text) >= 200
        with pytest.raises(ValidationError, match="INGLES"):
            make_spec(description=text)


def test_looks_spanish_heuristic():
    from app.functions.spec import looks_spanish
    assert looks_spanish("¿Qué cuenta está conectada?") and looks_spanish("la lista para el usuario")
    assert not looks_spanish("Lists the files of a folder; the path is optional and the limit defaults to 100.")
    assert not looks_spanish("")  # sin texto no es español (otra regla exige longitud)


def test_every_error_code_has_defaults():
    for code in ErrorCode:
        info = ErrorInfo.of(code, "x")
        assert info.code == code and info.user_action != "none"
    assert ErrorInfo.of(ErrorCode.rate_limited).retryable is True
    assert ErrorInfo.of(ErrorCode.auth_expired).retryable is False


def test_contract_has_the_ten_error_codes():
    assert {c.value for c in ErrorCode} == {
        "auth_expired", "missing_scope", "rate_limited", "not_found", "invalid_input",
        "upstream_changed", "upstream_down", "missing_connection", "account_selection_required", "access_denied",
    }


def test_result_shape_is_enforced():
    assert Result.success({"a": 1}).ok is True
    f = Result.failure(ErrorCode.not_found, "no existe")
    assert f.ok is False and f.error.code == ErrorCode.not_found
    with pytest.raises(ValidationError):
        Result(ok=True, error=ErrorInfo.of(ErrorCode.not_found))
    with pytest.raises(ValidationError):
        Result(ok=False)


def test_appspec_validations():
    auth = AuthSpec(type=AuthType.api_key, header_name="api-key", scheme=None)
    AppSpec(app="brevo", provider_keys=["brevo"], auth=auth)
    with pytest.raises(ValidationError):
        AppSpec(app="Brevo App", provider_keys=["brevo"], auth=auth)
    with pytest.raises(ValidationError):
        AppSpec(app="brevo", provider_keys=[], auth=auth)
    with pytest.raises(ValidationError):
        AuthSpec(type=AuthType.api_key, placement="cookie")
