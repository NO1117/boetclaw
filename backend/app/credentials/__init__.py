"""Encrypted credential vault for provider API keys."""

__all__ = ["CredentialVaultError", "credential_vault"]


def __getattr__(name: str):
    if name in {"CredentialVaultError", "credential_vault"}:
        from app.credentials.vault import CredentialVaultError, credential_vault

        return credential_vault if name == "credential_vault" else CredentialVaultError
    raise AttributeError(name)
