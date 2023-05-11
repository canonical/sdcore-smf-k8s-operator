# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library for the `fiveg_nrf` relation.

This library contains the Requires and Provides classes for handling the `fiveg_nrf`
interface.

The purpose of this library is to relate a charm claiming to provide
NRF information and another charm requiring this information.

## Getting Started
From a charm directory, fetch the library using `charmcraft`:

```shell
charmcraft fetch-lib charms.sdcore_nrf_operator.v0.fiveg_nrf
```

Add the following libraries to the charm's `requirements.txt` file:
- pydantic
- pytest-interface-tester

### Requirer charm
The requirer charm is the one requiring the NRF information.

Example:
```python

from ops.charm import CharmBase
from ops.main import main

from lib.charms.sdcore_nrf.v0.fiveg_nrf import NRFAvailableEvent, NRFRequires

logger = logging.getLogger(__name__)


class DummyFiveGNRFRequirerCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        self.nrf_requirer = NRFRequires(self, "fiveg-nrf")
        self.framework.observe(self.nrf_requirer.on.nrf_available, self._on_nrf_available)

    def _on_nrf_available(self, event: NRFAvailableEvent):
        nrf_url = event.url
        <do something with the nrf_url>


if __name__ == "__main__":
    main(DummyFiveGNRFRequirerCharm)
```

### Provider charm
The provider charm is the one requiring providing the information about the NRF.

Example:
```python

from ops.charm import CharmBase, RelationJoinedEvent
from ops.main import main

from lib.charms.sdcore_nrf.v0.fiveg_nrf import NRFProvides


class DummyFiveGNRFProviderCharm(CharmBase):

    NRF_URL = "https://nrf.example.com"

    def __init__(self, *args):
        super().__init__(*args)
        self.nrf_provider = NRFProvides(self, "fiveg-nrf")
        self.framework.observe(
            self.on.fiveg_nrf_relation_joined, self._on_fiveg_nrf_relation_joined
        )

    def _on_fiveg_nrf_relation_joined(self, event: RelationJoinedEvent):
        if self.unit.is_leader():
            self.nrf_provider.set_nrf_information(
                url=self.NRF_URL,
            )


if __name__ == "__main__":
    main(DummyFiveGNRFProviderCharm)
```

"""

# The unique Charmhub library identifier, never change it
LIBID = "cd132a12c2b34243bfd2bae8d08c32d6"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

import logging  # noqa: E402
from typing import Dict, Optional  # noqa: E402

from interface_tester.schema_base import DataBagSchema  # type: ignore[import]  # noqa: E402
from ops.charm import CharmBase, CharmEvents, RelationChangedEvent  # noqa: E402
from ops.framework import EventBase, EventSource, Handle, Object  # noqa: E402
from ops.model import Relation  # noqa: E402
from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError  # noqa: E402

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
            event: Juju event (RelationChangedEvent)

        Returns:
            None
        """
        if remote_app_relation_data := self._get_remote_app_relation_data(event.relation):
            self.on.nrf_available.emit(url=remote_app_relation_data["url"])

    def get_nrf_url(self) -> Optional[str]:
        """Returns NRF url.

        Returns:
            str: NRF url.
        """
        if remote_app_relation_data := self._get_remote_app_relation_data():
            return remote_app_relation_data.get("url")
        return None

    def _get_remote_app_relation_data(
        self, relation: Optional[Relation] = None
    ) -> Optional[Dict[str, str]]:
        """Get relation data for the remote application.

        Args:
            Relation: Juju relation object (optional).

        Returns:
            Dict: Relation data for the remote application
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
        if not self._relation_data_is_valid(remote_app_relation_data):
            logger.error("Invalid relation data: %s", remote_app_relation_data)
            return None
        return remote_app_relation_data

    @staticmethod
    def _relation_data_is_valid(relation_data: dict) -> bool:
        """Returns whether URL is valid.

        Args:
            str: URL to be validated.

        Returns:
            bool: True if URL is valid, False otherwise.
        """
        try:
            ProviderSchema(app=relation_data)
            return True
        except ValidationError:
            return False


class NRFProvides(Object):
    """Class to be instantiated by the charm providing the NRF data."""

    def __init__(self, charm: CharmBase, relation_name: str):
        """Init."""
        super().__init__(charm, relation_name)
        self.relation_name = relation_name
        self.charm = charm

    @staticmethod
    def _relation_data_is_valid(url: str) -> bool:
        """Returns whether URL is valid.

        Args:
            str: URL to be validated.

        Returns:
            bool: True if URL is valid, False otherwise.
        """
        try:
            ProviderSchema(app=ProviderAppData(url=url))  # type: ignore[arg-type]
            return True
        except ValidationError as e:
            logger.error("Invalid url: %s", e)
            return False

    def set_nrf_information(self, url: str) -> None:
        """Sets url in the application relation data.

        Args:
            str: NRF url
            int: Relation ID

        Returns:
            None
        """
        if not self.charm.unit.is_leader():
            raise RuntimeError("Unit must be leader to set application relation data.")
        relations = self.model.relations[self.relation_name]
        if not relations:
            raise RuntimeError(f"Relation {self.relation_name} not created yet.")
        if not self._relation_data_is_valid(url):
            raise ValueError(f"Invalid url: {url}")
        for relation in relations:
            relation.data[self.charm.app].update({"url": url})
