# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library for the `fiveg_nrf` relation.

This library contains the Requires and Provides classes for handling the `fiveg_nrf`
interface.

The purpose of this library is to relate a charm claiming to provide
NRF information and another charm requiring this information.

## Getting Started
From a charm directory, fetch the library using `charmcraft`:

```shell
charmcraft fetch-lib charms.sdcore_nrf.v0.fiveg_nrf
```

Add the following libraries to the charm's `requirements.txt` file:
- pydantic

### Requirer charm
The requirer charm is the one requiring the NRF information.

Example:
```python

from ops.charm import CharmBase
from ops.main import main

from charms.sdcore_nrf.v0.fiveg_nrf import NRFAvailableEvent, NRFRequires

logger = logging.getLogger(__name__)


class DummyFiveGNRFRequirerCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        self.nrf_requirer = NRFRequires(self, "fiveg-nrf")
        self.framework.observe(self.nrf_requirer.on.nrf_available, self._on_nrf_available)

    def _on_nrf_available(self, event: NRFAvailableEvent):
        nrf_url = self.nrf_requirer.nrf_url
        <do something with the nrf_url>


if __name__ == "__main__":
    main(DummyFiveGNRFRequirerCharm)
```

### Provider charm
The provider charm is the one providing the information about the NRF.

Example:
```python

from ops.charm import CharmBase, RelationJoinedEvent
from ops.main import main

from charms.sdcore_nrf.v0.fiveg_nrf import NRFProvides


class DummyFiveGNRFProviderCharm(CharmBase):

    NRF_URL = "https://nrf.example.com"

    def __init__(self, *args):
        super().__init__(*args)
        self.nrf_provider = NRFProvides(self, "fiveg-nrf")
        self.framework.observe(
            self.on.fiveg_nrf_relation_joined, self._on_fiveg_nrf_relation_joined
        )

    def _on_fiveg_nrf_relation_joined(self, event: RelationJoinedEvent):
        relation_id = event.relation.id
        self.nrf_provider.set_nrf_information(
            url=self.NRF_URL,
            relation_id=relation_id,
        )

    def _on_nrf_url_changed(
        self,
    ):
        self.nrf_provider.set_nrf_information_in_all_relations(
            url="https://different.nrf.com",
        )


if __name__ == "__main__":
    main(DummyFiveGNRFProviderCharm)
```

"""

import logging
from typing import Optional

from interface_tester.schema_base import DataBagSchema  # type: ignore[import]
from ops.charm import CharmBase, CharmEvents, RelationChangedEvent
from ops.framework import EventBase, EventSource, Handle, Object
from ops.model import Relation
from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError

# The unique Charmhub library identifier, never change it
LIBID = "cd132a12c2b34243bfd2bae8d08c32d6"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 5

PYDEPS = ["pydantic", "pytest-interface-tester"]


logger = logging.getLogger(__name__)

"""Schemas definition for the provider and requirer sides of the `fiveg_nrf` interface.
It exposes two interfaces.schema_base.DataBagSchema subclasses called:
- ProviderSchema
- RequirerSchema
Examples:
    ProviderSchema:
        unit: <empty>
        app: {"url": "https://nrf-example.com:1234"}
    RequirerSchema:
        unit: <empty>
        app:  <empty>
"""


class ProviderAppData(BaseModel):
    """Provider app data for fiveg_nrf."""

    url: AnyHttpUrl = Field(
        description="Url to reach the NRF.", examples=["https://nrf-example.com:1234"]
    )


class ProviderSchema(DataBagSchema):
    """Provider schema for fiveg_nrf."""

    app: ProviderAppData


def data_matches_provider_schema(data: dict) -> bool:
    """Returns whether data matches provider schema.

    Args:
        data (dict): Data to be validated.

    Returns:
        bool: True if data matches provider schema, False otherwise.
    """
    try:
        ProviderSchema(app=data)
        return True
    except ValidationError as e:
        logger.debug("Invalid data: %s", e)
        return False


class NRFAvailableEvent(EventBase):
    """Charm event emitted when a NRF is available. It carries the NRF url."""

    def __init__(self, handle: Handle, url: str):
        """Init."""
        super().__init__(handle)
        self.url = url

    def snapshot(self) -> dict:
        """Returns snapshot."""
        return {"url": self.url}

    def restore(self, snapshot: dict) -> None:
        """Restores snapshot."""
        self.url = snapshot["url"]


class NRFRequirerCharmEvents(CharmEvents):
    """List of events that the NRF requirer charm can leverage."""

    nrf_available = EventSource(NRFAvailableEvent)


class NRFRequires(Object):
    """Class to be instantiated by the NRF requirer charm."""

    on = NRFRequirerCharmEvents()

    def __init__(self, charm: CharmBase, relation_name: str):
        """Init."""
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.framework.observe(charm.on[relation_name].relation_changed, self._on_relation_changed)

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handler triggered on relation changed event.

        Args:
            event (RelationChangedEvent): Juju event.

        Returns:
            None
        """
        if remote_app_relation_data := self._get_remote_app_relation_data(event.relation):
            self.on.nrf_available.emit(url=remote_app_relation_data["url"])

    @property
    def nrf_url(self) -> Optional[str]:
        """Returns NRF url.

        Returns:
            str: NRF url.
        """
        if remote_app_relation_data := self._get_remote_app_relation_data():
            return remote_app_relation_data.get("url")
        return None

    def _get_remote_app_relation_data(self, relation: Optional[Relation] = None) -> Optional[dict]:
        """Get relation data for the remote application.

        Args:
            Relation: Juju relation object (optional).

        Returns:
            dict: Relation data for the remote application.
            or None if the relation data is invalid.
        """
        relation = relation or self.model.get_relation(self.relation_name)
        if not relation:
            logger.warning(f"No relation: {self.relation_name}")
            return None
        if not relation.app:
            logger.warning("No remote application in relation: %s", self.relation_name)
            return None
        remote_app_relation_data = dict(relation.data[relation.app])
        if not data_matches_provider_schema(remote_app_relation_data):
            logger.debug("Invalid relation data: %s", remote_app_relation_data)
            return None
        return remote_app_relation_data


class NRFProvides(Object):
    """Class to be instantiated by the charm providing the NRF data."""

    def __init__(self, charm: CharmBase, relation_name: str):
        """Init."""
        super().__init__(charm, relation_name)
        self.relation_name = relation_name
        self.charm = charm

    def set_nrf_information(
        self,
        url: str,
        relation_id: int,
    ) -> None:
        """Sets NRF url in the application(s) relation data.

        Args:
            url (str): NRF url.
            relation_id (int): Relation ID.

        Returns:
            None
        """
        if not self.charm.unit.is_leader():
            raise RuntimeError("Unit must be leader to set application relation data.")
        if not data_matches_provider_schema(data={"url": url}):
            raise ValueError(f"Invalid url: {url}")

        relation = self.model.get_relation(
            relation_name=self.relation_name, relation_id=relation_id
        )
        if not relation:
            raise RuntimeError(f"Relation {self.relation_name} not created yet.")
        if relation not in self.model.relations[self.relation_name]:
            raise RuntimeError(f"Relation {self.relation_name} not created yet.")
        relation.data[self.charm.app].update({"url": url})

    def set_nrf_information_in_all_relations(self, url: str) -> None:
        """Sets NRF url in applications for all applications.

        Args:
            url (str): NRF url.

        Returns:
            None
        """
        if not self.charm.unit.is_leader():
            raise RuntimeError("Unit must be leader to set application relation data.")
        if not data_matches_provider_schema(data={"url": url}):
            raise ValueError(f"Invalid url: {url}")

        relations = self.model.relations[self.relation_name]
        if not relations:
            raise RuntimeError(f"Relation {self.relation_name} not created yet.")
        for relation in relations:
            relation.data[self.charm.app].update({"url": url})
