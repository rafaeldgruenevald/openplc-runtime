from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from asyncua import Client, ua


ENDPOINT = os.environ.get(
    "OPCUA_ENDPOINT",
    (
        "opc.tcp://172.17.0.1:14840/"
        "openplc/opcua"
    ),
)

PROJECT_NAMESPACE_URI = (
    "urn:openplc:test:padim-device"
)

TARGET_IDENTIFIER = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal"
)

PUBLISHING_INTERVAL_MS = int(
    os.environ.get(
        "OPCUA_PUBLISHING_INTERVAL_MS",
        "100",
    )
)

TEST_DURATION_SECONDS = float(
    os.environ.get(
        "OPCUA_TEST_DURATION_SECONDS",
        "8",
    )
)

MINIMUM_NOTIFICATION_COUNT = int(
    os.environ.get(
        "OPCUA_MINIMUM_NOTIFICATIONS",
        "2",
    )
)


class SubscriptionHandler:
    def __init__(self) -> None:
        self.notifications: list[
            tuple[float, Any]
        ] = []

        self.change_event = (
            asyncio.Event()
        )

    def datachange_notification(
        self,
        node,
        value,
        data,
    ) -> None:
        timestamp = time.time()

        self.notifications.append(
            (
                timestamp,
                value,
            )
        )

        print(
            "DataChange:",
            f"time={timestamp:.6f}",
            f"node={node.nodeid}",
            f"value={value!r}",
            flush=True,
        )

        self.change_event.set()

    def event_notification(
        self,
        event,
    ) -> None:
        print(
            "Event:",
            repr(event),
            flush=True,
        )

    def status_change_notification(
        self,
        status,
    ) -> None:
        print(
            "StatusChange:",
            repr(status),
            flush=True,
        )


def values_are_numeric(
    values: list[Any],
) -> bool:
    return all(
        isinstance(
            value,
            (
                int,
                float,
            ),
        )
        and not isinstance(
            value,
            bool,
        )
        for value in values
    )


def unique_values(
    values: list[Any],
) -> list[Any]:
    result = []

    for value in values:
        if value not in result:
            result.append(value)

    return result


async def wait_for_notifications(
    handler: SubscriptionHandler,
) -> None:
    deadline = (
        asyncio.get_running_loop()
        .time()
        + TEST_DURATION_SECONDS
    )

    while True:
        if (
            len(handler.notifications)
            >= MINIMUM_NOTIFICATION_COUNT
            and len(
                unique_values(
                    [
                        value
                        for _, value
                        in handler.notifications
                    ]
                )
            )
            >= 2
        ):
            return

        remaining = (
            deadline
            - asyncio.get_running_loop()
            .time()
        )

        if remaining <= 0:
            return

        handler.change_event.clear()

        try:
            await asyncio.wait_for(
                handler.change_event.wait(),
                timeout=min(
                    remaining,
                    1.0,
                ),
            )
        except asyncio.TimeoutError:
            pass


async def main() -> None:
    print(
        "Runtime PADIM subscription test"
    )

    print(
        "Endpoint:",
        ENDPOINT,
    )

    print(
        "Publishing interval:",
        PUBLISHING_INTERVAL_MS,
        "ms",
    )

    print(
        "Test duration:",
        TEST_DURATION_SECONDS,
        "seconds",
    )

    print(
        "Minimum notifications:",
        MINIMUM_NOTIFICATION_COUNT,
    )

    handler = SubscriptionHandler()

    async with Client(
        url=ENDPOINT
    ) as client:
        namespace_index = (
            await client.get_namespace_index(
                PROJECT_NAMESPACE_URI
            )
        )

        node = client.get_node(
            ua.NodeId(
                TARGET_IDENTIFIER,
                namespace_index,
            )
        )

        node_class = (
            await node.read_node_class()
        )

        data_type = (
            await node.read_data_type()
        )

        value_rank = (
            await node.read_value_rank()
        )

        initial_value = (
            await node.read_value()
        )

        print()
        print(
            "Namespace index:",
            namespace_index,
        )

        print(
            "NodeId:",
            node.nodeid,
        )

        print(
            "NodeClass:",
            node_class,
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
            "Initial value:",
            repr(initial_value),
        )

        subscription = (
            await client.create_subscription(
                period=PUBLISHING_INTERVAL_MS,
                handler=handler,
            )
        )

        monitored_item = (
            await subscription.subscribe_data_change(
                node
            )
        )

        print()
        print(
            "Subscription created:",
            subscription.subscription_id,
        )

        print(
            "Monitored item:",
            monitored_item,
        )

        try:
            await wait_for_notifications(
                handler
            )
        finally:
            try:
                await subscription.unsubscribe(
                    monitored_item
                )
            finally:
                await subscription.delete()

        values = [
            value
            for _, value
            in handler.notifications
        ]

        distinct_values = unique_values(
            values
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
                "initial value is numeric",
                isinstance(
                    initial_value,
                    (
                        int,
                        float,
                    ),
                )
                and not isinstance(
                    initial_value,
                    bool,
                ),
            ),
            (
                (
                    "minimum notification "
                    "count reached"
                ),
                len(
                    handler.notifications
                )
                >= MINIMUM_NOTIFICATION_COUNT,
            ),
            (
                "all notification values are numeric",
                values_are_numeric(
                    values
                ),
            ),
            (
                "at least two distinct values received",
                len(distinct_values) >= 2,
            ),
        ]

        failed = False

        print()
        print(
            "Notification count:",
            len(
                handler.notifications
            ),
        )

        print(
            "Distinct value count:",
            len(distinct_values),
        )

        print(
            "Distinct values:",
            distinct_values,
        )

        print()
        print(
            "Runtime PADIM subscription validation:"
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
                "Runtime PADIM subscription failed"
            )

        print()
        print(
            "Runtime PADIM subscription passed"
        )


if __name__ == "__main__":
    asyncio.run(main())
