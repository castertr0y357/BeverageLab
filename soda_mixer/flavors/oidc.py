"""Authentik OIDC Authentication Backend for BeverageLab."""

import logging
from typing import Any, Dict
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import SuspiciousOperation
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

logger = logging.getLogger(__name__)
User = get_user_model()


class AuthentikOIDCBackend(OIDCAuthenticationBackend):
    """
    OIDC authentication backend integrated with Authentik.
    - Matches users by email (case-insensitive) or preferred_username.
    - Automatically sets unusable password for OIDC-created users.
    - Synchronizes first_name, last_name, and promotes to staff/superuser
      if the user belongs to the configured admin group.
    - Optionally enforces OIDC_REQUIRED_GROUP membership.
    """

    def filter_users_by_claims(self, claims: Dict[str, Any]):
        email = claims.get('email')
        preferred_username = claims.get('preferred_username')

        if email:
            users = User.objects.filter(email__iexact=email)
            if users.exists():
                return users

        if preferred_username:
            users = User.objects.filter(username__iexact=preferred_username)
            if users.exists():
                return users

        return User.objects.none()

    def verify_claims(self, claims: Dict[str, Any]) -> bool:
        scopes_verified = super().verify_claims(claims)
        if not scopes_verified:
            return False

        required_group = getattr(settings, 'OIDC_REQUIRED_GROUP', '')
        if required_group:
            user_groups = claims.get('groups', [])
            if required_group not in user_groups:
                logger.warning(
                    f"AuthentikOIDC - Access denied: User {claims.get('email')} lacks required group '{required_group}'"
                )
                return False

        return True

    def create_user(self, claims: Dict[str, Any]):
        email = claims.get('email', '')
        username = claims.get('preferred_username') or (email.split('@')[0] if email else 'oidc_user')

        # Ensure username uniqueness
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1

        user = User(username=username, email=email)
        user.set_unusable_password()
        self._sync_user_attributes(user, claims)
        user.save()
        logger.info(f"AuthentikOIDC - Created user '{user.username}' from Authentik claims")
        return user

    def update_user(self, user, claims: Dict[str, Any]):
        self._sync_user_attributes(user, claims)
        user.save()
        logger.info(f"AuthentikOIDC - Updated user '{user.username}' from Authentik claims")
        return user

    def _sync_user_attributes(self, user, claims: Dict[str, Any]):
        if 'name' in claims and claims['name']:
            parts = claims['name'].split(' ', 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ''
        else:
            if 'given_name' in claims:
                user.first_name = claims.get('given_name', '')
            if 'family_name' in claims:
                user.last_name = claims.get('family_name', '')

        if 'email' in claims and claims['email']:
            user.email = claims['email']

        admin_group = getattr(settings, 'OIDC_ADMIN_GROUP', 'authentik Admins')
        user_groups = claims.get('groups', [])
        if admin_group and admin_group in user_groups:
            user.is_staff = True
            user.is_superuser = True
        elif getattr(settings, 'OIDC_MAKE_ALL_USERS_STAFF', False):
            user.is_staff = True
