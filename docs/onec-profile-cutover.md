# Staged cutover of the profile endpoint to 1C

The new `OneCProfileView` is a **gateway**, not a copy or synchronizer of profile fields.

## Rollout

1. Deploy the backend code, without changing environment settings. The current profile route continues to use Django as a temporary fallback.
2. Ensure the 1C HTTP handlers GET/PATCH are installed in the *live* information base and test both manually.
3. Configure server-to-server authentication with `ONEC_API_USER` / `ONEC_API_PASSWORD`. For the explicitly restricted initial internal test only, set `ONEC_ALLOW_UNAUTHENTICATED_INTERNAL=1`; it works **only** with `ONEC_BASE_URL=http://host.docker.internal:8081` (not a public URL). This is NOT recommended for permanent operation.
4. Set `ONEC_PROFILE_GATEWAY_ENABLED=1` in the environment of the Django backend container and recreate it. All user profile GET/PATCH traffic now hits 1C; if 1C is unavailable, the endpoint errors rather than falling back to Django.
5. Test GET, PATCH, validation errors, 1C unavailability, identity mismatch, deactivation and revoked role. Change names in 1C Enterprise and observe the new values on GET through Django.

For fast rollback, set `ONEC_PROFILE_GATEWAY_ENABLED=0` and recreate Django. Do not continue using the legacy Django editor after editing profiles in 1C: a subsequent import from Django can overwrite changes. Remove the fallback after complete authorization/relations cutover.

## Frontend contract (unchanged)

`GET/PATCH /api/v1/users/profile/` returns
`{"user":{"id":...,"phone":...,"firstName":...,"lastName":...,"patronymic":...,"birthday":...,"roles":[...],"activeRole":...}}`.

PATCH accepts only `firstName`, `lastName`, `patronymic`, `birthday`.
It must not accept phone, roles, externalId, messengerUserId, isActive or id.

JWT still resolves to the existing local user **solely as a transitional identity carrier**; this work does not remove the foreign keys used by cars/orders and does not change authentication via MAX. The phone/UUID from that JWT context is checked against the 1C response before returning profile data. No profile fields are written to the Django DB while the gateway is enabled. Later, migrate the JWT identity lookup and foreign keys and remove the local user completely.
