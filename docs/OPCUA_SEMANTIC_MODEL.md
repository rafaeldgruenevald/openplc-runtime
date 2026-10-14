# OPC UA semantic model

A program can ship an OPC UA information model next to its code: standard
NodeSets (for example DI and PADIM), a project NodeSet, and bindings that tie
the model's variables to the compiled program. The plugin imports the models
before it builds the address space and keeps the bound nodes in sync with the
PLC.

## Where the files live

Everything travels inside `program.zip` and is extracted to `core/generated/`:

```
conf/opcua.json                  plugin configuration (enables the plugin)
conf/opcua_bindings.json         bindings (referenced by opcua.json)
models/Opc.Ua.Di.NodeSet2.xml    standard and project NodeSets, in import order
models/Opc.Ua.IRDI.NodeSet2.xml
models/Opc.Ua.PADIM.NodeSet2.xml
models/Project.NodeSet2.xml
```

## Configuration

`opcua.json` gets an optional `semantic_model` section. Paths are relative to
`core/generated`; a NodeSet must come after the models it requires.

```json
"semantic_model": {
  "nodesets": ["models/Opc.Ua.Di.NodeSet2.xml", "models/Project.NodeSet2.xml"],
  "bindings": "conf/opcua_bindings.json"
}
```

Without the section, `OPENPLC_OPCUA_NODESETS` and `OPENPLC_OPCUA_BINDINGS`
still work as a development fallback.

A model file must resolve below `core/generated` or `/opt/openplc/models`
(symlinks and `..` included), be a regular `.xml` (NodeSet) or `.json`
(bindings) file and not exceed 32 MiB (`model_paths.py`).

## Bindings

`opcua_bindings.json` (schema version `1.0`) has two lists.

`bindings` ties one imported Variable to one debug leaf (`arrayIndex`,
`elementIndex` from the compiler's `debug-map.json`). The OPC UA DataType of
the node must match the IEC type of the leaf.

`compositeBindings` builds a structured value from several leaves on every
client read. `Range` is supported: its `Low` and `High` fields are REAL or
LREAL leaves.

```json
{
  "id": "PT101.EURange",
  "nodeId": {"namespaceUri": "urn:project", "identifierType": "String",
             "identifier": "PT101.EURange"},
  "structure": "Range",
  "fields": {
    "Low":  {"symbol": "PT101.EURANGE.LOW",  "arrayIndex": 0, "elementIndex": 12,
             "datatype": "REAL", "size": 4},
    "High": {"symbol": "PT101.EURANGE.HIGH", "arrayIndex": 0, "elementIndex": 13,
             "datatype": "REAL", "size": 4}
  }
}
```

A composite node is read-only. A subscription on it reports the value at
creation only; reads are always live.

## Known limits

- The official DI 1.05 NodeSet contains nine `FunctionalGroupType` instances
  with no parent and no references. asyncua cannot import them
  (`BadParentNodeIdInvalid`), so the loader skips exactly those and logs their
  NodeIds. The file is not modified.
- asyncua reads a value element whose text is `None` as Null. A NodeSet that
  writes `LocalizedText` or `ExtensionObject` values without whitespace
  before the first child loses them on import; write them indented.
- The server listens on the container address, not on `0.0.0.0`, as before.

## Tests

```bash
docker run --rm -v "$PWD/core:/workdir/core" -w /workdir <image> bash -c '
  venvs/opcua/bin/pip install -q pytest pytest-asyncio
  cd core/src/drivers/plugins/python/opcua &&
  /workdir/venvs/opcua/bin/python -m pytest -q tests --deselect tests/test_subscription_client.py'
```
