"""NRF Interface."""

# TODO: Create and fetch the interface.

import logging
from typing import Optional

from ops.charm import CharmBase, CharmEvents, RelationChangedEvent
from ops.framework import EventBase, EventSource, Object
from ops.model import ModelError

logger = logging.getLogger(__name__)


# The unique Charmhub library identifier, never change it
LIBID = "9a57f2993b264a14a09a36066058c768"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 2


class NRFAvailableEvent(EventBase):
    """Dataclass for NRF available events."""

    def __init__(self, handle, url: str):
        """Sets url."""
        super().__init__(handle)
        self.url = url

    def snapshot(self) -> dict:
        """Returns event data."""
        return {"url": self.url}

    def restore(self, snapshot) -> None:
        """Restores event data."""
        self.url = snapshot["url"]


class NRFRequirerCharmEvents(CharmEvents):
    """All custom events for the NRFRequirer."""

    nrf_available = EventSource(NRFAvailableEvent)


class NRFProvides(Object):
    """NRF provides interface."""

    def __init__(self, charm: CharmBase, relationship_name: str):
        self.relationship_name = relationship_name
        super().__init__(charm, relationship_name)

    def set_info(self, url: str) -> None:
        """Sets the url for the NRF service."""
        relations = self.model.relations[self.relationship_name]
        for relation in relations:
            try:
                relation.data[self.model.app]["url"] = url
            except ModelError as e:
                logger.debug("Error setting relation data: %s", e)
                continue


class NRFRequires(Object):
    """NRF Requires Interface."""

    on = NRFRequirerCharmEvents()

    def __init__(self, charm: CharmBase, relationship_name: str):
        self.relationship_name = relationship_name
        self.charm = charm
        super().__init__(charm, relationship_name)
        self.framework.observe(
            charm.on[relationship_name].relation_changed, self._on_relation_changed
        )

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        """Triggered everytime there's a change in relation data.

        Args:
            event (RelationChangedEvent): Juju event

        Returns:
            None
        """
        url = event.relation.data[event.app].get("url")
        if url:
            self.on.nrf_available.emit(url=url)

    def get_nrf_url(self) -> Optional[str]:
        """Returns NRF url."""
        for relation in self.model.relations[self.relationship_name]:
            if not relation.data:
                continue
            try:
                remote_application_relation_data = relation.data[relation.app]
            except ModelError as e:
                logger.debug("Error reading relation data: %s", e)
                continue
            if not remote_application_relation_data:
                continue
            return remote_application_relation_data.get("url", None)
        return None
