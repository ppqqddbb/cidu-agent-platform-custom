import datetime
from unittest.mock import patch

from core.plugin.entities.plugin import (
    PluginCategory,
    PluginDeclaration,
    PluginEntity,
    PluginInstallationSource,
    PluginResourceRequirements,
)
from core.plugin.impl.exc import PluginDaemonClientSideError
from core.plugin.plugin_service import PluginService
from core.tools.entities.common_entities import I18nObject
from core.tools.entities.tool_entities import ToolProviderEntity, ToolProviderIdentity


def _plugin_entity(plugin_id: str, category: PluginCategory) -> PluginEntity:
    return PluginEntity(
        id=f"{plugin_id}-entity",
        created_at=datetime.datetime(2023, 1, 1, 0, 0, 0),
        updated_at=datetime.datetime(2023, 1, 1, 0, 0, 0),
        tenant_id="test-tenant",
        endpoints_setups=0,
        endpoints_active=0,
        runtime_type="remote",
        source=PluginInstallationSource.Package,
        meta={},
        plugin_id=plugin_id,
        plugin_unique_identifier=f"test-org/{plugin_id}:1.0.0@checksum",
        version="1.0.0",
        checksum="checksum",
        name=plugin_id,
        installation_id=f"{plugin_id}-install",
        declaration=PluginDeclaration(
            version="1.0.0",
            author="test-author",
            name=plugin_id,
            description=I18nObject(en_US=plugin_id, zh_Hans=plugin_id),
            icon="icon.png",
            label=I18nObject(en_US=plugin_id, zh_Hans=plugin_id),
            category=category,
            created_at=datetime.datetime(2023, 1, 1, 0, 0, 0),
            resource=PluginResourceRequirements(memory=512, permission=None),
            plugins=PluginDeclaration.Plugins(),
            tool=(
                ToolProviderEntity(
                    identity=ToolProviderIdentity(
                        author="test-author",
                        name=plugin_id,
                        description=I18nObject(en_US=plugin_id, zh_Hans=plugin_id),
                        icon="icon.png",
                        label=I18nObject(en_US=plugin_id, zh_Hans=plugin_id),
                    )
                )
                if category == PluginCategory.Tool
                else None
            ),
            meta=PluginDeclaration.Meta(version="1.0.0"),
        ),
    )


def test_list_by_category_falls_back_when_daemon_category_route_is_missing():
    tool_plugin = _plugin_entity("tool-plugin", PluginCategory.Tool)
    model_plugin = _plugin_entity("model-plugin", PluginCategory.Model)

    with (
        patch(
            "core.plugin.plugin_service.PluginInstaller.list_plugins_by_category",
            side_effect=PluginDaemonClientSideError('{"code":"not_found","message":"route not found"}'),
        ) as category_list_mock,
        patch(
            "core.plugin.plugin_service.PluginInstaller.list_plugins",
            return_value=[tool_plugin, model_plugin],
        ) as list_mock,
    ):
        result = PluginService.list_by_category("test-tenant", PluginCategory.Tool, page=1, page_size=10)

    category_list_mock.assert_called_once_with("test-tenant", PluginCategory.Tool, 1, 10)
    list_mock.assert_called_once_with("test-tenant")
    assert result.list == [tool_plugin]
    assert result.has_more is False
