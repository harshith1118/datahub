"""DataHub GMS client for reading schema diffs, lineage, and writing remediation tags.

Uses DataHub's public GraphQL API and REST MCP endpoint directly.
"""

import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


class DataHubClient:
    """Client for interacting with DataHub GMS via GraphQL and REST APIs.

    Args:
        gms_url: DataHub GMS base URL. Falls back to DATAHUB_GMS_URL env var,
            then http://localhost:8080.
        token: DataHub API token. Falls back to DATAHUB_TOKEN env var.
        dry_run: When True, log intended actions without making API calls.
    """

    def __init__(
        self,
        gms_url: str | None = None,
        token: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.gms_url = (gms_url or os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")).rstrip("/")
        self.token = token or os.environ.get("DATAHUB_TOKEN", "")
        self.dry_run = dry_run
        self._headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.token:
            self._headers["Authorization"] = f"Bearer {self.token}"

    def _graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a GraphQL query against the DataHub GMS endpoint."""
        url = f"{self.gms_url}/api/graphql"
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        logger.debug("POST %s with query=%.120s", url, query)
        resp = requests.post(url, json=payload, headers=self._headers, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if "errors" in data:
            raise RuntimeError(f"DataHub GraphQL error: {data['errors']}")
        return data.get("data", {})

    def fetch_schema_diffs(self, dataset_urn: str) -> dict[str, Any]:
        """Query DataHub for the current schema metadata of a dataset.

        Returns the dataset's schema fields, types, and version info.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] fetch_schema_diffs(%s)", dataset_urn)
            return {"dry_run": True, "dataset_urn": dataset_urn}

        query = """
        query GetSchema($urn: String!) {
            dataset(urn: $urn) {
                urn
                name
                schemaMetadata {
                    name
                    version
                    fields {
                        fieldPath
                        type
                        nativeDataType
                        nullable
                    }
                }
            }
        }
        """
        return self._graphql(query, {"urn": dataset_urn})

    def fetch_lineage(self, dataset_urn: str) -> dict[str, Any]:
        """Fetch upstream and downstream lineage edges for a dataset.

        Returns both upstream (sources) and downstream (dependents) entities.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] fetch_lineage(%s)", dataset_urn)
            return {"dry_run": True, "dataset_urn": dataset_urn}

        query = """
        query GetLineage($urn: String!) {
            dataset(urn: $urn) {
                urn
                upstream: relationships(
                    input: {
                        types: ["DownstreamOf"]
                        direction: OUTGOING
                        start: 0
                        count: 100
                    }
                ) {
                    relationships {
                        type
                        entity {
                            ... on Dataset {
                                urn
                                name
                            }
                        }
                    }
                }
                downstream: relationships(
                    input: {
                        types: ["DownstreamOf"]
                        direction: INCOMING
                        start: 0
                        count: 100
                    }
                ) {
                    relationships {
                        type
                        entity {
                            ... on Dataset {
                                urn
                                name
                            }
                        }
                    }
                }
            }
        }
        """
        return self._graphql(query, {"urn": dataset_urn})

    def write_remediation_tag(self, dataset_urn: str, tag: str) -> bool:
        """Write a tag (e.g. ``STATUS: FIX_PENDING_PR_42``) to a DataHub dataset.

        Uses the ``addTag`` GraphQL mutation.
        Returns True on success.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] write_remediation_tag(%s, %s)", dataset_urn, tag)
            return True

        mutation = """
        mutation AddTag($input: TagAssociationInput!) {
            addTag(input: $input)
        }
        """
        variables = {
            "input": {
                "tagUrn": f"urn:li:tag:{tag}",
                "resourceUrn": dataset_urn,
            }
        }
        self._graphql(mutation, variables)
        logger.info("Tag '%s' written to %s", tag, dataset_urn)
        return True

    def write_incident_link(self, dataset_urn: str, pr_url: str) -> bool:
        """Attach an incident note with a PR link to a dataset's institutional memory.

        Uses the ``createGraph`` (institutionalMemory) mutation or falls back to
        the MCP REST endpoint.
        Returns True on success.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] write_incident_link(%s, %s)", dataset_urn, pr_url)
            return True

        url = f"{self.gms_url}/api/entities/v1"
        note = json.dumps({"pr_url": pr_url, "status": "fix_pending"})
        payload = {
            "entityType": "dataset",
            "entityUrn": dataset_urn,
            "aspect": {
                "institutionalMemory": {
                    "elements": [
                        {
                            "url": pr_url,
                            "description": f"Remediation PR for schema breaking change — {pr_url}",
                            "label": "Remediation PR",
                            "note": note,
                            "createdBy": "urn:li:corpuser:datahub-sentinel",
                        }
                    ]
                }
            },
        }
        logger.debug("POST %s with payload=%.200s", url, payload)
        resp = requests.post(url, json=payload, headers=self._headers, timeout=30)
        resp.raise_for_status()
        logger.info("Incident link written to %s -> %s", dataset_urn, pr_url)
        return True