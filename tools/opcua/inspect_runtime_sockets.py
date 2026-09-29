from pathlib import Path
import os


PROCESS_NAMES = {
    "plc_main",
    "webserver.app",
}


def read_command_line(
    process_directory,
):
    path = (
        process_directory
        / "cmdline"
    )

    try:
        return (
            path.read_bytes()
            .replace(
                bytes([0]),
                b" ",
            )
            .decode(
                "utf-8",
                errors="replace",
            )
            .strip()
        )
    except (
        FileNotFoundError,
        PermissionError,
        ProcessLookupError,
    ):
        return ""


def collect_process_sockets():
    results = []

    for process_directory in Path(
        "/proc"
    ).iterdir():
        if not process_directory.name.isdigit():
            continue

        command_line = read_command_line(
            process_directory
        )

        if not any(
            name in command_line
            for name in PROCESS_NAMES
        ):
            continue

        file_descriptor_directory = (
            process_directory
            / "fd"
        )

        try:
            descriptors = list(
                file_descriptor_directory
                .iterdir()
            )
        except (
            FileNotFoundError,
            PermissionError,
        ):
            continue

        for descriptor in descriptors:
            try:
                target = os.readlink(
                    descriptor
                )
            except (
                FileNotFoundError,
                PermissionError,
            ):
                continue

            if not target.startswith(
                "socket:["
            ):
                continue

            inode = target.removeprefix(
                "socket:["
            ).removesuffix(
                "]"
            )

            results.append(
                {
                    "pid": int(
                        process_directory.name
                    ),
                    "command": command_line,
                    "descriptor": int(
                        descriptor.name
                    ),
                    "inode": inode,
                }
            )

    return results


def parse_ipv4_endpoint(
    value,
):
    address_hex, port_hex = (
        value.split(":")
    )

    address_bytes = bytes.fromhex(
        address_hex
    )

    address = ".".join(
        str(byte)
        for byte in reversed(
            address_bytes
        )
    )

    port = int(
        port_hex,
        16,
    )

    return f"{address}:{port}"


def load_inet_sockets():
    sockets = {}

    tables = [
        (
            "tcp",
            Path("/proc/net/tcp"),
        ),
        (
            "udp",
            Path("/proc/net/udp"),
        ),
    ]

    for protocol, path in tables:
        if not path.exists():
            continue

        lines = path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()

        for line in lines[1:]:
            fields = line.split()

            if len(fields) < 10:
                continue

            local_endpoint = (
                parse_ipv4_endpoint(
                    fields[1]
                )
            )

            remote_endpoint = (
                parse_ipv4_endpoint(
                    fields[2]
                )
            )

            state = fields[3]
            inode = fields[9]

            sockets[inode] = {
                "protocol": protocol,
                "local": local_endpoint,
                "remote": remote_endpoint,
                "state": state,
            }

    return sockets


def load_unix_sockets():
    sockets = {}

    path = Path(
        "/proc/net/unix"
    )

    if not path.exists():
        return sockets

    lines = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    for line in lines[1:]:
        fields = line.split()

        if len(fields) < 7:
            continue

        inode = fields[6]
        socket_path = (
            fields[7]
            if len(fields) > 7
            else ""
        )

        sockets[inode] = {
            "protocol": "unix",
            "path": socket_path,
        }

    return sockets


def main():
    process_sockets = (
        collect_process_sockets()
    )

    inet_sockets = (
        load_inet_sockets()
    )

    unix_sockets = (
        load_unix_sockets()
    )

    if not process_sockets:
        print(
            "No matching process sockets"
        )
        return

    for item in sorted(
        process_sockets,
        key=lambda value: (
            value["pid"],
            value["descriptor"],
        ),
    ):
        print()
        print("PID:", item["pid"])
        print(
            "Command:",
            item["command"],
        )
        print(
            "Descriptor:",
            item["descriptor"],
        )
        print(
            "Socket inode:",
            item["inode"],
        )

        inode = item["inode"]

        if inode in inet_sockets:
            details = inet_sockets[inode]

            print(
                "Protocol:",
                details["protocol"],
            )
            print(
                "Local:",
                details["local"],
            )
            print(
                "Remote:",
                details["remote"],
            )
            print(
                "State:",
                details["state"],
            )

        elif inode in unix_sockets:
            details = unix_sockets[inode]

            print(
                "Protocol:",
                details["protocol"],
            )
            print(
                "Path:",
                details["path"],
            )

        else:
            print(
                "Socket details:"
                " not found"
            )


if __name__ == "__main__":
    main()
