from __future__ import annotations

import asyncio
import os

from asyncua import Client, ua


ENDPOINT = os.environ.get(
    "OPCUA_ENDPOINT",
    (
        "opc.tcp://127.0.0.1:14840/"
        "openplc/opcua"
    ),
)

PROJECT_NAMESPACE_URI = (
    "urn:openplc:test:padim-device"
)

ANALOG_SIGNAL_IDENTIFIER = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal"
)

ENGINEERING_UNITS_IDENTIFIER = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal.EngineeringUnits"
)

EU_RANGE_IDENTIFIER = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal.EURange"
)


async def main() -> None:
    print(
        "Connecting to:",
        ENDPOINT,
    )

    async with Client(
        url=ENDPOINT
    ) as client:
        namespace_index = (
            await client.get_namespace_index(
                PROJECT_NAMESPACE_URI
            )
        )

        analog_signal = client.get_node(
            ua.NodeId(
                ANALOG_SIGNAL_IDENTIFIER,
                namespace_index,
            )
        )

        engineering_units = client.get_node(
            ua.NodeId(
                ENGINEERING_UNITS_IDENTIFIER,
                namespace_index,
            )
        )

        eu_range = client.get_node(
            ua.NodeId(
                EU_RANGE_IDENTIFIER,
                namespace_index,
            )
        )

        node_class = (
            await analog_signal.read_node_class()
        )

        data_type = (
            await analog_signal.read_data_type()
        )

        value_rank = (
            await analog_signal.read_value_rank()
        )

        value = (
            await analog_signal.read_value()
        )

        access_level = (
            await analog_signal.read_access_level()
        )

        user_access_level = (
            await analog_signal
            .read_user_access_level()
        )

        type_definition = (
            await analog_signal
            .read_type_definition()
        )

        units = (
            await engineering_units.read_value()
        )

        measurement_range = (
            await eu_range.read_value()
        )

        checks = [
            (
                "namespace resolved",
                namespace_index > 0,
            ),
            (
                "target is Variable",
                node_class
                == ua.NodeClass.Variable,
            ),
            (
                "DataType is Float",
                data_type
                == ua.NodeId(
                    ua.ObjectIds.Float
                ),
            ),
            (
                "ValueRank is scalar-compatible",
                value_rank
                in {
                    ua.ValueRank.Scalar,
                    ua.ValueRank.Any,
                    -1,
                    -2,
                },
            ),
            (
                "value is numeric",
                isinstance(
                    value,
                    (
                        int,
                        float,
                    ),
                ),
            ),
            (
                "EngineeringUnits is bar",
                units.DisplayName.Text
                == "bar",
            ),
            (
                "EURange is 0 to 16",
                measurement_range.Low
                == 0.0
                and measurement_range.High
                == 16.0,
            ),
        ]

        failed = False

        print()
        print(
            "Namespace index:",
            namespace_index,
        )
        print(
            "NodeId:",
            analog_signal.nodeid,
        )
        print(
            "NodeClass:",
            node_class,
        )
        print(
            "TypeDefinition:",
            type_definition,
        )
        print(
            "DataType:",
            data_type,
        )
        print(
            "ValueRank:",
            value_rank,
        )
        print(
            "Value:",
            repr(value),
        )
        print(
            "AccessLevel:",
            access_level,
        )
        print(
            "UserAccessLevel:",
            user_access_level,
        )
        print(
            "EngineeringUnits:",
            repr(units),
        )
        print(
            "EURange:",
            repr(measurement_range),
        )

        print()
        print(
            "Runtime PADIM read validation:"
        )

        for name, passed in checks:
            print(
                "  PASS" if passed else "  FAIL",
                name,
            )

            if not passed:
                failed = True

        if failed:
            raise SystemExit(
                "Runtime PADIM read failed"
            )

        print()
        print(
            "Runtime PADIM read passed"
        )


if __name__ == "__main__":
    asyncio.run(main())
