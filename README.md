# keysight_E36312A_DCSweep

Aplicacion Python para controlar una fuente Keysight E36312A/E36300 de 3 canales
mediante PyVISA/SCPI. La primera version incluye interfaz grafica con PySide6,
control manual por canal, barridos DC con grafica I vs V en tiempo real,
exportacion CSV, limites de seguridad y un instrumento mock para desarrollo sin
hardware conectado.

## Estado actual

Implementado:

- Conexion VISA con listado de recursos, recurso manual y `*IDN?`.
- Modo `Mock Instrument` para probar la GUI sin una fuente real.
- Control manual de CH1, CH2 y CH3: voltaje, limite de corriente, ON/OFF y medicion.
- Botones `All OFF`, `Ramp to 0 V and OFF` y `Emergency Stop`.
- Barrido DC por canal con `V_start`, `V_stop`, `V_step`, `I_limit`, `settle time` y tolerancia de compliance.
- Grafica I vs V en tiempo real con pyqtgraph.
- Exportacion CSV con las columnas:
  `timestamp_iso, t_s, channel, Vset_V, Vmeas_V, Imeas_A, P_W, compliance_flag, notes`.
- Apagado seguro al cerrar la app por default.

Preparado para etapa 2:

- MOSFET output curves: `ID` vs `VDS` para varios `VGS`.
- MOSFET transfer curve: `ID` vs `VGS`, `gm`, `Vth` y `sqrt(ID)`.
- BJT curve tracer: `IC` vs `VCE` usando resistencia externa de base.

## Instalacion

Requisitos:

- Python 3.10 o superior.
- Backend VISA instalado segun tu sistema.
- Para hardware real, NI-VISA, Keysight IO Libraries o `pyvisa-py` con soporte
  adecuado para el bus usado.
- En Linux con USBTMC y `pyvisa-py`, tambien se requiere `pyusb` y permisos de
  usuario sobre el dispositivo USB.

Linux/macOS/Windows:

```bash
git clone https://github.com/ROMERUU-dev/keysight_E36312A_DCSweep.git
cd keysight_E36312A_DCSweep
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows PowerShell/CMD
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

En algunas instalaciones de Linux el ejecutable del sistema se llama `python3`;
usa `python3 -m venv .venv` si `python` no existe hasta activar el entorno.

## Ejecutar la app

Con instrumento real:

```bash
python app.py
```

Con instrumento simulado:

```bash
python app.py --mock
```

El modo mock responde a `*IDN?`, simula set voltage, set current, medicion de
voltaje/corriente y compliance simple con una carga interna de 1 kohm. Es el modo
recomendado para validar la interfaz antes de conectar hardware.

## Conexion a Keysight E36312A

1. Conecta la fuente por USB/LAN/GPIB segun tu entorno.
2. Verifica que el recurso VISA aparezca en la app con `Refresh`.
3. Si no aparece, escribe el recurso manualmente en el campo editable, por ejemplo:

```text
USB0::0x2A8D::0x1102::<serial>::INSTR
```

4. Presiona `Connect` y confirma que `IDN` muestre la respuesta del instrumento.

El ultimo recurso usado se guarda en `config.json`, que esta ignorado por git para
evitar publicar identificadores locales o numeros de serie.

### Linux USBTMC permissions

Si `lsusb` ve la fuente pero PyVISA no lista ningun recurso, revisa permisos:

```bash
lsusb | grep -i keysight
ls -l /dev/usbtmc* /dev/bus/usb/*/* 2>/dev/null | grep -E 'usbtmc|2a8d' || true
```

Para permitir acceso al usuario del grupo `plugdev`, crea una regla udev:

```bash
sudo tee /etc/udev/rules.d/99-keysight-e36312a.rules >/dev/null <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="2a8d", ATTR{idProduct}=="1102", GROUP="plugdev", MODE="0660"
KERNEL=="usbtmc*", ATTRS{idVendor}=="2a8d", ATTRS{idProduct}=="1102", GROUP="plugdev", MODE="0660"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Desconecta y reconecta la fuente despues de instalar la regla. Si necesitas una
prueba temporal sin reiniciar reglas, puedes usar:

```bash
sudo chmod g+rw /dev/usbtmc0 /dev/bus/usb/001/007
```

Ajusta `001/007` al bus/dispositivo que reporte `lsusb`.

## Ejemplo de barrido DC

1. Conecta en modo real o `--mock`.
2. En `DC Sweep`, selecciona `CH1`.
3. Configura:
   - `V start`: 0 V
   - `V stop`: 1 V
   - `V step`: 0.1 V
   - `I limit`: 0.1 A
   - `Settle time`: 0.1 s
   - `Compliance tolerance`: 0.02
4. Presiona `Start Sweep`.
5. Al terminar, presiona `Export CSV`.

El CSV se guarda por default como:

```text
runs/sweeps/dc_sweep_latest.csv
```

La carpeta `runs/` esta ignorada por git.

## Seguridad

- La app arranca con salidas apagadas cuando se conecta.
- Al cerrar, intenta poner voltajes en 0 V, apagar salidas y cerrar la comunicacion.
- Ante excepciones VISA/SCPI, intenta apagar salidas y dejar el instrumento seguro.
- `Emergency Stop` detiene barridos activos y ejecuta apagado seguro.
- Limites conservadores por default:
  - CH1: 0 a 6 V, 0 a 5 A, 30 W max.
  - CH2: 0 a 25 V, 0 a 1 A, 25 W max.
  - CH3: 0 a 25 V, 0 a 1 A, 25 W max.

Verifica estos limites contra tu configuracion fisica antes de conectar un DUT.
Usa fusibles, resistencias limitadoras o proteccion externa cuando sea necesario.

## Pruebas

```bash
python -m pytest
```

Las pruebas cubren:

- Generacion de rangos de barrido.
- Validacion de limites de seguridad.
- Exportacion CSV.
- Modo mock y barrido con compliance.

## Arquitectura

```text
app.py
src/instruments/visa_manager.py
src/instruments/keysight_supply.py
src/instruments/scpi_profiles.py
src/measurements/dc_sweep.py
src/measurements/safety.py
src/measurements/data_export.py
src/measurements/transistor_curves.py
src/gui/
tests/
```

Los comandos SCPI estan centralizados en `src/instruments/scpi_profiles.py`.
El acceso al instrumento debe pasar por `KeysightSupply`, no por comandos SCPI
dispersos en la GUI.

## Roadmap

- Agregar perfiles SCPI alternativos si algun modelo E36300 requiere cambios
  menores de comandos.
- Guardar configuraciones de limite por canal en un panel editable.
- Exportar cada barrido con nombre unico por timestamp.
- Implementar familias de curvas MOSFET `ID` vs `VDS`.
- Implementar curva de transferencia MOSFET con estimacion aproximada de `gm`
  y `Vth`.
- Implementar curve tracer BJT con resistencia externa de base y calculo de beta.
- Agregar pruebas con mocks de errores VISA/SCPI.
