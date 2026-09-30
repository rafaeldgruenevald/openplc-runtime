from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


NODESET_PATH = Path(
    "models/generated/"
    "Test.PADIMDevice.NodeSet2.xml"
)

PROJECT_MODEL_URI = (
    "urn:openplc:test:padim-device"
)

REQUIRED_IDENTIFIERS = {
    "PT101",
    "PT101.Manufacturer",
    "PT101.ManufacturerUri",
    "PT101.Model",
    "PT101.SerialNumber",
    "PT101.SoftwareRevision",
    "PT101.HardwareRevision",
    "PT101.ProductCode",
    "PT101.DeviceHealth",
    "PT101.ProductInstanceUri",
    "PT101.AssetId",
    "PT101.RevisionCounter",
    "PT101.SignalSet",
    "PT101.SignalSet.Pressure",
    "PT101.SignalSet.Pressure.SignalTag",
    (
        "PT101.SignalSet.Pressure."
        "AnalogSignal"
    ),
    (
        "PT101.SignalSet.Pressure."
        "AnalogSignal.EngineeringUnits"
    ),
    (
        "PT101.SignalSet.Pressure."
        "AnalogSignal.EURange"
    ),
}


def local_name(
    element,
) -> str:
    return element.tag.split("}")[-1]


def main() -> None:
    if not NODESET_PATH.is_file():
        raise FileNotFoundError(
            f"Missing NodeSet: {NODESET_PATH}"
        )

    root = ET.parse(
        NODESET_PATH
    ).getroot()

    counts = {}
    identifiers = set()
    project_models = []
    required_models = []

    for element in root:
        name = local_name(
            element
        )

        counts[name] = (
            counts.get(name, 0) + 1
        )

        node_id = element.attrib.get(
            "NodeId",
            "",
        )

        if ";s=PT101" in node_id:
            identifiers.add(
                node_id.split(
                    ";s=",
                    1,
                )[1]
            )

        if name != "Models":
            continue

        for model in element:
            if local_name(model) != "Model":
                continue

            if (
                model.attrib.get(
                    "ModelUri"
                )
                != PROJECT_MODEL_URI
            ):
                continue

            project_models.append(
                model.attrib
            )

            for required in model:
                if (
                    local_name(required)
                    == "RequiredModel"
                ):
                    required_models.append(
                        required.attrib
                    )

    missing = (
        REQUIRED_IDENTIFIERS
        - identifiers
    )

    unexpected = (
        identifiers
        - REQUIRED_IDENTIFIERS
    )

    checks = [
        (
            "XML root is UANodeSet",
            local_name(root)
            == "UANodeSet",
        ),
        (
            "project node count is 18",
            len(identifiers) == 18,
        ),
        (
            "all expected identifiers exist",
            not missing,
        ),
        (
            "no unexpected identifiers exist",
            not unexpected,
        ),
        (
            "one Models element exists",
            counts.get(
                "Models",
                0,
            )
            == 1,
        ),
        (
            "one project Model exists",
            len(project_models) == 1,
        ),
        (
            "three RequiredModel declarations",
            len(required_models) == 3,
        ),
        (
            "SignalTag exists",
            (
                "PT101.SignalSet."
                "Pressure.SignalTag"
            )
            in identifiers,
        ),
    ]

    failed = False

    print(
        "NodeSet:",
        NODESET_PATH,
    )
    print(
        "Size:",
        NODESET_PATH.stat().st_size,
    )

    print()
    print("Element counts:")

    for name in sorted(counts):
        print(
            " ",
            name,
            counts[name],
        )

    print()
    print("Project NodeIds:")

    for identifier in sorted(
        identifiers
    ):
        print(
            " ",
            identifier,
        )

    print()
    print("Project models:")

    for model in project_models:
        print(
            " ",
            model,
        )

    print()
    print("Required models:")

    for model in required_models:
        print(
            " ",
            model,
        )

    print()
    print("Validation:")

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    if missing:
        print(
            "Missing identifiers:",
            sorted(missing),
        )

    if unexpected:
        print(
            "Unexpected identifiers:",
            sorted(unexpected),
        )

    if failed:
        raise SystemExit(
            "Generated PADIM NodeSet "
            "inspection failed"
        )

    print()
    print(
        "Generated PADIM NodeSet "
        "inspection passed"
    )


if __name__ == "__main__":
    main()
