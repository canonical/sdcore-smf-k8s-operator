# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


"""Library for the `sdcore_config` relation.

This library contains the Requires and Provides classes for handling the `sdcore_config`
interface.

The purpose of this library is to relate charms claiming
to be able to provide or consume the information to access the webui GRPC address
for configuration purposes in SD-Core.

## Getting Started
From a charm directory, fetch the library using `charmcraft`:

```shell
charmcraft fetch-lib charms.sdcore_webui_k8s.v0.sdcore_config
```

Add the following libraries to the charm's `requirements.txt` file:
- pydantic
- pytest-interface-tester

### Requirer charm
The requirer charm is the one requiring the Webui information.

Example:
```python

import logging

from ops.charm import CharmBase
from ops.main import main

from lib.charms.sdcore_webui_k8s.v0.sdcore_config import (
    SdcoreConfigRequires,
    WebuiBroken,
    WebuiUrlAvailable,
)

logger = logging.getLogger(__name__)


class DummySdcoreConfigRequirerCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        self.webui_requirer = SdcoreConfigRequires(
            self, "sdcore_config"
        )
        self.framework.observe(
            self.webui_requirer.on.webui_url_available,
            self._on_webui_url_available
        )
        self.framework.observe(self.webui_requirer.on.webui_broken, self._on_webui_broken)

    def _on_webui_url_available(self, event: WebuiUrlAvailable):
        logging.info(f"Webui URL from the event: {event.webui_url}")
        logging.info(f"Webui URL from the property: {self.webui_requirer.webui_url}")

    def _on_webui_broken(self, event: WebuiBroken) -> None:
        logging.info(f"Received {event}")


if __name__ == "__main__":
    main(DummySdcoreConfigRequirerCharm)
```

### Provider charm
The provider charm is the one providing the information about the Webui.

Example:
```python

from ops.charm import CharmBase, RelationJoinedEvent
from ops.main import main

from lib.charms.sdcore_webui_k8s.v0.sdcore_config import SdcoreConfigProvides


class DummySdcoreConfigProviderCharm(CharmBase):

    WEBUI_URL = "sdcore-webui-k8s:9876"

    def __init__(self, *args):
        super().__init__(*args)
        self.webui_url_provider = SdcoreConfigProvides(self, "sdcore_config")
        self.framework.observe(
            self.on.sdcore_config_relation_joined, self._on_sdcore_config_relation_joined
        )

    def _on_sdcore_config_relation_joined(self, event: RelationJoinedEvent):
        relation_id = event.relation.id
        self.webui_url_provider.set_webui_url(
            webui_url=self.WEBUI_URL,
            relation_id=relation_id,
        )


if __name__ == "__main__":
    main(DummySdcoreConfigProviderCharm)
```

"""
import logging
from typing import Optional

from interface_tester.schema_base import DataBagSchema  # type: ignore[import]
from ops.charm import CharmBase, CharmEvents, RelationBrokenEvent, RelationChangedEvent
from ops.framework import EventBase, EventSource, Handle, Object
from ops.model import Relation
from pydantic import BaseModel, Field, ValidationError

# The unique Charmhub library identifier, never change it
LIBID = "87b8ff625f5544ad9985552df3fb6b6b"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

logger = logging.getLogger(__name__)

"""Schemas definition for the provider and requirer sides of the `sdcore_config` interface.
It exposes two interfaces.schema_base.DataBagSchema subclasses called:
- ProviderSchema
- RequirerSchema
Examples:
    ProviderSchema:
        unit: <empty>
        app: {
            "webui_url": "sdcore-webui-k8s:9876",
        }
    RequirerSchema:
        unit: <empty>
        app:  <empty>
"""


class SdcoreConfigProviderAppData(BaseModel):
    """Provider application data for sdcore_config."""
    webui_url: str = Field(
        description="GRPC address of the Webui including Webui hostname and a fixed GRPC port.",
        examples=["sdcore-webui-k8s:9876"]
    )


class ProviderSchema(DataBagSchema):
    """The schema for the provider side of the sdcore-config interface."""
    app: SdcoreConfigProviderAppData


def data_is_valid(data: dict) -> bool:
    """Return whether data is valid.

    Args:
        data (dict): Data to be validated.

    Returns:
        bool: True if data is valid, False otherwise.
    """
    try:
        ProviderSchema(app=data)
        return True
    except ValidationError as e:
        logger.error("Invalid data: %s", e)
        return False


class WebuiUrlAvailable(EventBase):
    """Charm event emitted when the Webui URL is available."""

    def __init__(self, handle: Handle, webui_url: str):
        """Init."""
        super().__init__(handle)
        self.webui_url = webui_url

    def snapshot(self) -> dict:
        """Return snapshot."""
        return {
            "webui_url": self.webui_url,
        }

    def restore(self, snapshot: dict) -> None:
        """Restore snapshot."""
        self.webui_url = snapshot["webui_url"]


class WebuiBroken(EventBase):
    """Charm event emitted when the Webui goes down."""

    def __init__(self, handle: Handle):
        """Init."""
        super().__init__(handle)


class SdcoreConfigRequirerCharmEvents(CharmEvents):
    """List of events that the SD-Core config requirer charm can leverage."""

    webui_url_available = EventSource(WebuiUrlAvailable)
    webui_broken = EventSource(WebuiBroken)


class SdcoreConfigRequires(Object):
    """Class to be instantiated by the SD-Core config requirer charm."""

    on = SdcoreConfigRequirerCharmEvents()

    def __init__(self, charm: CharmBase, relation_name: str):
        """Init."""
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.framework.observe(charm.on[relation_name].relation_changed, self._on_relation_changed)
        self.framework.observe(charm.on[relation_name].relation_broken, self._on_relation_broken)

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle relation changed event.

        Args:
            event (RelationChangedEvent): Juju event.

        Returns:
            None
        """
        if remote_app_relation_data := self._get_remote_app_relation_data(event.relation):
            self.on.webui_url_available.emit(
                webui_url=remote_app_relation_data,
            )

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the Sdcore config relation broken event.

        Args:
            event (RelationBrokenEvent): Juju event.
        """
        self.on.webui_broken.emit()

    @property
    def webui_url(self) -> Optional[str]:
        """Return the address of the webui GRPC endpoint.

        Returns:
            str: Endpoint address.
        """
        return self._get_remote_app_relation_data()

    def _get_remote_app_relation_data(
        self, relation: Optional[Relation] = None
    ) -> Optional[str]:
        """Get relation data for the remote application.

        Args:
            relation: Juju relation object (optional).

        Returns:
        str: Relation data for the remote application
            or None if the relation data is invalid.
        """
        relation = relation or self.model.get_relation(self.relation_name)

        if not relation:
            logger.error("No relation: %s", self.relation_name)
            return None

        if not relation.app:
            logger.warning("No remote application in relation: %s", self.relation_name)
            return None

        remote_app_relation_data = dict(relation.data[relation.app])

        if not data_is_valid(remote_app_relation_data):
            logger.error("Invalid relation data: %s", remote_app_relation_data)
            return None

        return remote_app_relation_data["webui_url"]


class SdcoreConfigProvides(Object):
    """Class to be instantiated by the charm providing the SD-Core Webui URL."""

    def __init__(self, charm: CharmBase, relation_name: str):
        """Init."""
        super().__init__(charm, relation_name)
        self.relation_name = relation_name
        self.charm = charm

    def set_webui_url(self, webui_url: str, relation_id: int) -> None:
        """Set the address of the Webui GRPC endpoint.

        Args:
            webui_url (str): Webui GRPC service address.
            relation_id (int): Relation ID.

        Returns:
            None
        """
        if not self.charm.unit.is_leader():
            raise RuntimeError("Unit must be leader to set application relation data.")

        if not data_is_valid(data={"webui_url": webui_url}):
            raise ValueError(f"Invalid url: {webui_url}")

        relation = self.model.get_relation(
            relation_name=self.relation_name, relation_id=relation_id
        )

        if not relation:
            raise RuntimeError(f"Relation {self.relation_name} not created yet.")

        if relation not in self.model.relations[self.relation_name]:
            raise RuntimeError(f"Relation {self.relation_name} not created yet.")

        relation.data[self.charm.app].update({"webui_url": webui_url})

    def set_webui_url_in_all_relations(self, webui_url: str) -> None:
        """Set Webui URL in applications for all applications.

        Args:
            webui_url (str): Webui GRPC service address
        Returns:
            None
        """
        if not self.charm.unit.is_leader():
            raise RuntimeError("Unit must be leader to set application relation data.")

        if not data_is_valid(data={"webui_url": webui_url}):
            raise ValueError(f"Invalid url: {webui_url}")

        relations = self.model.relations[self.relation_name]

        if not relations:
            raise RuntimeError(f"Relation {self.relation_name} not created yet.")

        for relation in relations:
            relation.data[self.charm.app].update({"webui_url": webui_url})
