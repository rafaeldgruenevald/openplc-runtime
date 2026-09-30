TYPE
  ST_LOCALIZED_TEXT : STRUCT
    Locale : STRING;
    Text : STRING;
  END_STRUCT;
  E_DEVICE_HEALTH : (HEALTH_NORMAL, HEALTH_FAILURE, HEALTH_CHECK_FUNCTION, HEALTH_OFF_SPEC, HEALTH_MAINTENANCE_REQUIRED);
  ST_RANGE : STRUCT
    Low : LREAL;
    High : LREAL;
  END_STRUCT;
  ST_EU_INFORMATION : STRUCT
    NamespaceUri : STRING;
    UnitId : DINT;
    DisplayName : ST_LOCALIZED_TEXT;
    Description : ST_LOCALIZED_TEXT;
  END_STRUCT;
  ST_ANALOG_VALUE : STRUCT
    Value : REAL;
    EURange : ST_RANGE;
    EngineeringUnits : ST_EU_INFORMATION;
  END_STRUCT;
  ST_ANALOG_SIGNAL : STRUCT
    Tag : STRING;
    ProcessValue : ST_ANALOG_VALUE;
  END_STRUCT;
  ST_PADIM_DEVICE : STRUCT
    Manufacturer : ST_LOCALIZED_TEXT;
    Model : ST_LOCALIZED_TEXT;
    DeviceDiagnosticStatus : E_DEVICE_HEALTH;
    ManufacturerUri : STRING;
    SerialNumber : STRING;
    SoftwareRevision : STRING;
    HardwareRevision : STRING;
    ProductCode : STRING;
    ProductInstanceUri : STRING;
    AssetId : STRING;
    RevisionCounter : DINT;
    PressureSignal : ST_ANALOG_SIGNAL;
  END_STRUCT;
END_TYPE

PROGRAM main
  VAR
    PT101 : ST_PADIM_DEVICE;
    Initialized : BOOL := FALSE;
    Rising : BOOL := TRUE;
    CycleCount : UDINT := 0;
  END_VAR

  IF NOT Initialized THEN
      PT101.Manufacturer.Locale := 'en-US';
      PT101.Manufacturer.Text := 'OpenPLC PoC';

      PT101.Model.Locale := 'en-US';
      PT101.Model.Text := 'PADIM Pressure Transmitter';

      PT101.DeviceDiagnosticStatus := HEALTH_NORMAL;

      PT101.ManufacturerUri := 'urn:openplc:opas:poc';
      PT101.SerialNumber := 'SIM-PT101-001';
      PT101.SoftwareRevision := '0.1.0';
      PT101.HardwareRevision := 'SIM-1';
      PT101.ProductCode := 'OPENPLC-PADIM-PT';
      PT101.ProductInstanceUri := 'urn:openplc:device:pt101';
      PT101.AssetId := 'PT101';
      PT101.RevisionCounter := 1;

      PT101.PressureSignal.Tag := 'PT101';
      PT101.PressureSignal.ProcessValue.Value := 0.0;

      PT101.PressureSignal.ProcessValue.EURange.Low := 0.0;
      PT101.PressureSignal.ProcessValue.EURange.High := 16.0;

      PT101.PressureSignal.ProcessValue.EngineeringUnits.NamespaceUri :=
          'http://www.opcfoundation.org/UA/units/un/cefact';

      PT101.PressureSignal.ProcessValue.EngineeringUnits.UnitId := 0;

      PT101.PressureSignal.ProcessValue.EngineeringUnits.DisplayName.Locale :=
          'en-US';

      PT101.PressureSignal.ProcessValue.EngineeringUnits.DisplayName.Text :=
          'bar';

      PT101.PressureSignal.ProcessValue.EngineeringUnits.Description.Locale :=
          'en-US';

      PT101.PressureSignal.ProcessValue.EngineeringUnits.Description.Text :=
          'Pressure in bar';

      Initialized := TRUE;
  END_IF;


  CycleCount := CycleCount + 1;


  IF Rising THEN
      PT101.PressureSignal.ProcessValue.Value :=
          PT101.PressureSignal.ProcessValue.Value + 0.01;

      IF PT101.PressureSignal.ProcessValue.Value >= 16.0 THEN
          PT101.PressureSignal.ProcessValue.Value := 16.0;
          Rising := FALSE;
      END_IF;
  ELSE
      PT101.PressureSignal.ProcessValue.Value :=
          PT101.PressureSignal.ProcessValue.Value - 0.01;

      IF PT101.PressureSignal.ProcessValue.Value <= 0.0 THEN
          PT101.PressureSignal.ProcessValue.Value := 0.0;
          Rising := TRUE;
      END_IF;
  END_IF;


  IF PT101.PressureSignal.ProcessValue.Value > 15.0 THEN
      PT101.DeviceDiagnosticStatus := HEALTH_OFF_SPEC;
  ELSE
      PT101.DeviceDiagnosticStatus := HEALTH_NORMAL;
  END_IF;
END_PROGRAM


CONFIGURATION Config0

  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#20ms,PRIORITY := 1);
    PROGRAM instance0 WITH task0 : main;
  END_RESOURCE
END_CONFIGURATION
