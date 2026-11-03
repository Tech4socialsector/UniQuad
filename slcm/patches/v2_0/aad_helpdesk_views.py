"""Pin the default ticket views for existing AAD / AAD Staff agents
(see slcm.api.helpdesk_views)."""

from slcm.api.helpdesk_views import sync_all_ticket_views


def execute():
    sync_all_ticket_views()
