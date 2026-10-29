# Cualquier modelo del Model Zoo en el smartcam de la Kria KV260 (opción `-a`)

Guía de referencia para llevar **un modelo del Vitis AI Model Zoo 2.5** a la aplicación smartcam: elegirlo según los fps que se necesitan, compilarlo para el DPU de la KV260, configurarlo en VVAS y medir si cumple. Reemplaza a `yolov3_smartcam_kv260.md`: lo que se verificó con YOLOv3 se conserva (secciones 6 y 8) y el procedimiento se escribió con variables para que valga para cualquier modelo.

Basada en:

- [Customizing the AI Models Used in the Application](https://xilinx.github.io/kria-apps-docs/kv260/2022.1/build/html/docs/smartcamera/docs/customize_ai_models.html)
- [Setting Up the Board and Application Deployment](https://xilinx.github.io/kria-apps-docs/kv260/2022.1/build/html/docs/smartcamera/docs/app_deployment.html)
- [Vitis AI Model Zoo 2.5 (README)](https://github.com/Xilinx/Vitis-AI/tree/v2.5/model_zoo): tablas de fps por tarjeta
- [VVAS 2.0, plug-ins](https://xilinx.github.io/VVAS/2.0/build/html/docs/common/common_plugins.html): campo `model-class`
- [VVAS, Supporting Deep Learning Models](https://xilinx.github.io/dc-video-analytics-sdk/html/v1.0/adding_models.html): modelo → clase VVAS
- [UG1414, Compiling for DPU](https://docs.amd.com/r/2.0-English/ug1414-vitis-ai/Compiling-for-DPU): comando de compilación por framework

**Etiquetas de confianza usadas en la guía**

- **[verificado]**: se probó en la Kria con YOLOv3.
- **[por verificar]**: sale de la documentación, no se ha probado en esta placa. Confirmarlo la primera vez que se use y pasarlo a [verificado].

---

## 1. Resumen

| Tema | Resultado |
|---|---|
| Alcance | Cualquier modelo del Model Zoo 2.5 cuya clase soporte VVAS, compilado para el DPU **B3136** de smartcam |
| Flujo | Elegir (sección 3) → descargar y compilar (4) → mean/scale/etiquetas (4.5 y 4.6) → configs VVAS y contenedor (5) → medir (7) |
| Caso 1: YOLOv3 COCO 416 | Funciona, pero da **≈10 fps** (cuello de botella: el DPU). Sirve para video de 10 fps [verificado] |
| Caso 2: SSD-MobileNetV2 COCO 300 | Candidato para **videovigilancia a 30 fps**: estimación de DPU ≈60 fps. Pendiente de probar (sección 9) |
| Regla para 30 fps estables | El modelo debe dar **≥45 fps solo en el DPU** (`xdputil benchmark`), es decir 1.5 veces el objetivo |
| Lo que cambia entre modelos | Nombre, xmodel compilado, prototxt, `label.json`, `mean/scale` y `model-class` (sección 12) |

---

## 2. Entorno

| Elemento | Detalle |
|---|---|
| Tarjeta | Kria KV260, Ubuntu 22.04, firmware `kv260-smartcam` |
| DPU | `DPUCZDX8G_ISA1_B3136`, fingerprint `0x101000016010406` |
| IP de la Kria | `192.168.137.50` (cable directo con ICS desde Windows) |
| PC host | HP Victus con Windows, WSL2 (Ubuntu 20.04), Docker |
| Compilación | Contenedor `xilinx/vitis-ai-cpu:2.5.0` (la guía solo soporta Vitis AI 2.5.0) |
| Ejecución en la Kria | Contenedor `xilinx/smartcam:2022.1` |
| Cámaras | MIPI AR1335 y una cámara USB en `/dev/media0` |
| Mac | Solo para clonar el repo Vitis-AI y leer el `model.yaml` del tag `v2.5` |

**Reparto de trabajo**

| Dónde | Qué se hace |
|---|---|
| PC (WSL2) | Descargar el modelo, compilarlo, armar el paquete |
| PowerShell (Windows) | `scp` hacia la Kria y `ffplay`/`ffmpeg` como cliente. **WSL no alcanza la red `192.168.137.x`** |
| Kria, fuera del contenedor | Cargar el overlay, escribir las configs, lanzar Docker |
| Kria, dentro del contenedor | `smartcam`, `xdputil` |

**Variables.** Todos los comandos de la guía usan estas variables; solo cambian al cambiar de modelo.

| Variable      | Qué es                                                                                                                                    | Caso 1: YOLOv3                      | Caso 2: SSD-MobileNetV2                                       |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- | ------------------------------------------------------------- |
| `ZOO_ID`      | Carpeta en `model_zoo/model-list/` del repo (nombre largo, con GOPs y versión)                                                            | `tf2_yolov3_coco_416_416_65.9G_2.5` | `tf_ssdmobilenetv2_coco_300_300_3.75G_2.5`                    |
| `NAME`        | Nombre corto del modelo: carpeta del `.tar.gz` de kv260, xmodel y prototxt. Sale del campo `name:` de la entrada `kv260` del `model.yaml` | `yolov3_coco_416_tf2`               | `ssd_mobilenet_v2_coco_tf` [por verificar en el `model.yaml`] |
| `AITASK`      | Valor de `-a`, nombre de la carpeta de configs de VVAS. Se elige                                                                          | `yolov3_coco`                       | `ssd_mobilenet_v2_coco`                                       |
| `MODEL_CLASS` | Clase de VVAS (sección 3.3)                                                                                                               | `YOLOV3`                            | `TFSSD`                                                       |

> **Ojo con `NAME`:** no siempre coincide con el nombre de la tabla de rendimiento del README. Con YOLOv3 la tabla dice `yolov3_coco_tf2` y el paquete real se llama `yolov3_coco_416_tf2`. Se toma siempre del `model.yaml`.

---

## 3. Elegir el modelo

### 3.1 Presupuesto de fps

- El DPU de smartcam es **B3136**, más chico que el B4096F con el que el README del Model Zoo mide la KV260. Con YOLOv3 la relación medida fue 10.2 / 14.1 ≈ **0.72** [verificado con un solo modelo].
- Estimación rápida: `fps en smartcam ≈ 0.7 × fps de la tabla "Performance on Kria KV260 SOM"` del README. En modelos muy ligeros la CPU (pre y post-proceso) pesa más y la estimación es optimista [por verificar].
- Para 30 fps **estables** se pide un margen de 1.5×: **≥45 fps solo en el DPU**. Ese margen cubre el post-proceso en CPU, el dibujo de cajas, el codificador y las fluctuaciones.

### 3.2 Candidatos de detección (Model Zoo 2.5)

Datos del README del Model Zoo; la columna de estimación aplica el factor 0.7.

| `ZOO_ID` | GOPs | Entrada | mAP cuantizado | fps KV260 B4096F (1 hilo / multi) | Estimado B3136 (1 hilo / multi) | ¿30 fps estables? |
|---|---|---|---|---|---|---|
| `tf_ssdlite_mobilenetv2_coco_300_300_1.5G_2.5` | 1.5 | 300×300 | 0.209 | 111.5 / 161.4 | ≈78 / ≈113 | Sí, margen amplio |
| `tf_ssdmobilenetv1_coco_300_300_2.47G_2.5` | 2.47 | 300×300 | 0.210 | 119.1 / 172.2 | ≈83 / ≈121 | Sí, margen amplio |
| **`tf_ssdmobilenetv2_coco_300_300_3.75G_2.5`** | 3.75 | 300×300 | 0.211 | 87.7 / 112.7 | **≈61 / ≈79** | **Sí, margen 2×** |
| `tf_ssdinceptionv2_coco_300_300_9.62G_2.5` | 9.62 | 300×300 | 0.236 | 42.1 / 47.2 | ≈29 / ≈33 | Justo, sin margen |
| `pt_OFA-yolo_coco_640_640_0.5_24.62G_2.5` | 24.62 | 640×640 | 0.378 | 29.2 / 35.5 | ≈20 / ≈25 | No |
| `pt_FairMOT_mixed_640_480_0.5_36G_2.5` (detección + seguimiento) | 36 | 640×480 | MOTA 58.1 % | 24.2 / 27.0 | ≈17 / ≈19 | No |
| `tf2_yolov3_coco_416_416_65.9G_2.5` | 65.9 | 416×416 | 0.331 | 14.1 / 14.8 | **10.2 medido** | No [verificado] |

La sección "Surveillance" del Model Zoo trae modelos de rostro, ReID, conteo de multitudes y FairMOT; ninguno es un detector general que llegue a 30 fps en este DPU, por eso se elige entre los detectores de la tabla.

### 3.3 Compatibilidad con VVAS (`model-class`)

smartcam solo ejecuta modelos cuya clase conozca el plug-in `vvas_xdpuinfer`. La documentación de VVAS 2.0 lista `YOLOV3`, `FACEDETECT`, `CLASSIFICATION`, `SSD`, `REFINEDET`, `TFSSD` y `YOLOV2`. VVAS 3.0 añade más clases; **no se verificó cuáles trae la imagen `smartcam:2022.1`** [por verificar].

Correspondencia modelo → clase según la documentación de VVAS:

| Modelo | `model-class` |
|---|---|
| `ssd_mobilenet_v1_coco_tf`, `ssd_mobilenet_v2_coco_tf`, `ssdlite_mobilenet_v2_coco_tf`, `ssd_inception_v2_coco_tf`, `ssd_resnet_50_fpn_coco_tf` | `TFSSD` |
| `yolov3_coco_416_tf2`, `yolov3_voc_tf`, `face_mask_detection_pt` | `YOLOV3` |
| `densebox_*` | `FACEDETECT` |
| `resnet*`, `chen_color_resnet18_pt` | `CLASSIFICATION` |
| `refinedet_*` | `REFINEDET` |

Esa tabla se validó en VVAS 3.0; en la smartcam 2022.1 (VVAS 2.0) hay que confirmarlo [por verificar]. Si una clase no existe, la salida es `RAWTENSOR` (tensores sin post-proceso), que ya no es "correr el modelo con cajas" sino escribir el post-proceso aparte.

### 3.4 Decisión para videovigilancia a 30 fps

**Modelo: `ssd_mobilenet_v2_coco_tf`** (`tf_ssdmobilenetv2_coco_300_300_3.75G_2.5`).

- Estimación de DPU ≈60 fps con un hilo: 2× el objetivo.
- Es un modelo que la documentación de VVAS usa en sus ejemplos (clase `TFSSD`).
- COCO incluye las clases típicas de vigilancia: `person`, `car`, `truck`, `bus`, `motorcycle`, `bicycle`, `backpack`, `handbag`, `suitcase`.
- Respaldo si el pipeline completo no llega a 30 fps: `ssdlite_mobilenet_v2_coco_tf` (2.5× menos GOPs, mismo mAP cuantizado).

**Límite conocido:** la entrada de 300×300 hace que objetos pequeños o lejanos en una imagen de 1080p se pierdan. Es el precio de los 30 fps con este DPU. Los modelos de mayor precisión (OFA-YOLO, YOLOv3) no llegan a la tasa.

---

## 4. Preparar el modelo (PC host)

### 4.1 Localizar el `model.yaml`

El `model.yaml` de la rama `master` ya no trae los xmodels para KV260. Se usa el tag `v2.5` del repositorio:

```bash
cd ~/ruta/a/Vitis-AI && git checkout v2.5
export ZOO_ID=tf_ssdmobilenetv2_coco_300_300_3.75G_2.5
cat model_zoo/model-list/$ZOO_ID/model.yaml
```

Cada entrada tiene `name`, `board`, `download link` y `checksum`. Se necesitan dos:

- `board: GPU` → el zip con el modelo float y el cuantizado.
- `board: zcu102 & zcu104 & kv260` → el `.tar.gz`, **solo para el `.prototxt`**. Su `.xmodel` está compilado para otro DPU (B4096): no usarlo.

### 4.2 Descargar y verificar

```bash
Y=model_zoo/model-list/$ZOO_ID/model.yaml
GPU_URL=$(awk '/board: GPU/{f=1} f&&/download link/{print $3; exit}' $Y)
GPU_MD5=$(awk '/board: GPU/{f=1} f&&/checksum/{print $2; exit}' $Y)
KV_URL=$(awk '/board: zcu102 & zcu104 & kv260/{f=1} f&&/download link/{print $3; exit}' $Y)
KV_MD5=$(awk '/board: zcu102 & zcu104 & kv260/{f=1} f&&/checksum/{print $2; exit}' $Y)
export NAME=$(awk '/name:/{n=$NF} /board: zcu102 & zcu104 & kv260/{print n; exit}' $Y)
echo "NAME=$NAME"; echo "$GPU_URL $GPU_MD5"; echo "$KV_URL $KV_MD5"
```

Revisar que las cinco líneas tengan sentido (si alguna sale vacía, copiar el valor a mano del `model.yaml`). Después, en una carpeta de trabajo:

```bash
mkdir -p ~/Kria_Prjs/$NAME && cd ~/Kria_Prjs/$NAME
wget "$GPU_URL" -O $ZOO_ID.zip && wget "$KV_URL" -O $NAME-kv260.tar.gz
echo "$GPU_MD5  $ZOO_ID.zip" | md5sum -c - ; echo "$KV_MD5  $NAME-kv260.tar.gz" | md5sum -c -
unzip -q $ZOO_ID.zip && tar -xzf $NAME-kv260.tar.gz
find . -name "*.h5" -o -name "*.pb" -o -name "*.prototxt" -o -name "*.xmodel"
```

Resultado esperado del `find` (YOLOv3 como ejemplo [verificado]):

```
./tf2_yolov3_coco_416_416_65.9G_2.5/quantized/quantized.h5
./tf2_yolov3_coco_416_416_65.9G_2.5/float/yolov3.h5
./yolov3_coco_416_tf2/yolov3_coco_416_tf2.prototxt
./yolov3_coco_416_tf2/yolov3_coco_416_tf2.xmodel          <- NO usar: es para otro DPU (B4096)
./yolov3_coco_416_tf2_acc/...                              <- variante, tampoco se usa
```

Checksums del caso 1 [verificado]: zip GPU `137583eae110e06e164d44fa2eab7a0b`, tar.gz kv260 `ae417567b1462c7d5b6708285643f140`.

### 4.3 `arch.json`

```bash
cd ~/Kria_Prjs/$NAME && printf '{\n    "fingerprint":"0x101000016010406"\n}\n' > arch.json && cat arch.json
```

(La guía oficial indica obtenerlo con `xdputil query` en la Kria; el valor es el mismo para todos los modelos.)

### 4.4 Compilar para el DPU B3136

El comando depende del framework, que se lee en el prefijo de `ZOO_ID`:

| Prefijo | Framework | Archivo que se compila | Entorno conda (dentro del contenedor) | Comando |
|---|---|---|---|---|
| `tf2_` | TensorFlow 2 | `quantized/quantized.h5` | `vitis-ai-tensorflow2` | `vai_c_tensorflow2 -m <h5> -a arch.json -o compiled -n $NAME` |
| `tf_` | TensorFlow 1 | `quantized/quantize_eval_model.pb` | `vitis-ai-tensorflow` | `vai_c_tensorflow -f <pb> -a arch.json -o compiled -n $NAME` |
| `pt_` | PyTorch | `quantized/*_int.xmodel` | `vitis-ai-pytorch` | `vai_c_xir -x <xmodel> -a arch.json -o compiled -n $NAME` |

Los tres comandos salen de UG1414. Para el caso `tf_`, UG1414 indica que `quantize_eval_model.pb` es la entrada del compilador XIR; si la carpeta `quantized/` trae también un `deploy_model.pb`, ese no es el que se usa [por verificar con el zip concreto].

Lanzar el contenedor de Vitis AI montando la carpeta de trabajo:

```bash
cd ~/Kria_Prjs/$NAME && docker run -it --rm -v "$(pwd)":/workspace -w /workspace xilinx/vitis-ai-cpu:2.5.0 bash
```

Dentro del contenedor (las variables no pasan solas: reescribirlas) y como ejemplo del caso 1 [verificado]:

```bash
export NAME=yolov3_coco_416_tf2
conda activate vitis-ai-tensorflow2 && vai_c_tensorflow2 -m ./tf2_yolov3_coco_416_416_65.9G_2.5/quantized/quantized.h5 -a arch.json -o ./compiled -n $NAME --options '{"input_shape": "1,416,416,3"}' && ls -lh ./compiled
```

Y para el caso 2 (TF 1) [por verificar]:

```bash
export NAME=ssd_mobilenet_v2_coco_tf
conda activate vitis-ai-tensorflow && vai_c_tensorflow -f ./tf_ssdmobilenetv2_coco_300_300_3.75G_2.5/quantized/quantize_eval_model.pb -a arch.json -o ./compiled -n $NAME && ls -lh ./compiled
```

> **`--options` solo si hace falta.** La guía oficial no lo usa. En YOLOv3 fue necesario porque el `quantized.h5` guarda la entrada como `[1, None, None, 3]` y el compilador falla (sección 10). Si con otro modelo aparece `Invalid shape of input layer`, añadir `--options '{"input_shape": "1,H,W,3"}'` con la entrada del modelo (para el SSD de este caso: `1,300,300,3`).

Resultado esperado: `compiled/$NAME.xmodel`. En YOLOv3: ≈63 MB y 5 subgrafos (1 DPU, 3 CPU, 1 de usuario). Es normal que haya subgrafos de CPU: son las operaciones que el DPU no soporta.

### 4.5 `mean` y `scale` del preprocesado

El preprocesado de smartcam lo hace un kernel de la parte lógica (`pp_pipeline_accel`) y recibe valores ya ajustados al modelo cuantizado.

1. Leer **mean** y **scale** del prototxt (`kernel { mean: ... scale: ... }`). **El orden en el prototxt es B, G, R** (no R, G, B).
2. Leer el **fixpos del tensor de entrada** del xmodel compilado:

```bash
xdputil xmodel ./compiled/$NAME.xmodel -l
```

3. Calcular, por canal:

```
scale_config = scale_prototxt × 2^fixpos
mean_config  = mean_prototxt
```

4. Pasar a `preprocess.json`: la primera `mean` del prototxt es `mean_b`, la segunda `mean_g`, la tercera `mean_r` (igual con `scale`).

**Comprobación de cordura** [por verificar como regla general]: el kernel entrega enteros de 8 bits, así que para un píxel entre 0 y 255 debe cumplirse `(255 − mean) × scale_config ≤ 127` y `(0 − mean) × scale_config ≥ −128`.

| Modelo | mean (prototxt) | scale (prototxt) | fixpos de entrada | `scale_config` | Estado |
|---|---|---|---|---|---|
| `yolov3_coco_416_tf2` | 0, 0, 0 | 0.00390625 | 6 | 0.25 | [verificado] |
| `refinedet_pruned_0_96` (guía oficial) | 104, 117, 123 | 1.0 | −1 | 0.5 | Oficial |
| `ssd_mobilenet_v2_coco_tf` | leer del prototxt | leer del prototxt | leer del xmodel | calcular | Pendiente (sección 9) |

El prototxt de YOLOv3 también trae `num_classes: 80`, `conf_threshold: 0.3`, `nms_threshold: 0.45` y `layer_name: "58", "66", "74"` (los tres tensores de salida). Se usan tal cual: no se copian a ningún JSON de VVAS.

### 4.6 `label.json`

VVAS necesita un `label.json` con el nombre de cada clase. Se genera con este esquema (el índice es el que devuelve el modelo):

```bash
cd ~/Kria_Prjs/$NAME && mkdir -p ${NAME}_pkg && cp compiled/$NAME.xmodel $NAME/$NAME.prototxt ${NAME}_pkg/
python3 - << 'EOF'
import json, os
NAME = os.environ["NAME"]
names_by_index = {}   # <- pegar aquí el diccionario del modelo (Anexo A)

n = max(names_by_index) + 1
labels = [{"label": i, "name": names_by_index.get(i, "N/A"),
           "display_name": names_by_index.get(i, "N/A")} for i in range(n)]
json.dump({"model-name": NAME, "num-labels": n, "labels": labels},
          open(f"{NAME}_pkg/label.json", "w"), indent=1)
print(n, "etiquetas")
EOF
ls -l ${NAME}_pkg
```

**Cuidado con el índice.** Los modelos YOLO de COCO numeran desde 0 (`0 = person`, 80 clases). Los SSD de TensorFlow usan los identificadores de categoría de COCO (`1 = person`, con huecos, 91 posiciones) [por verificar]. Si en pantalla las etiquetas salen desplazadas (la persona se llama `bicycle`), el índice está corrido y hay que ajustar el diccionario. El Anexo A trae las dos listas.

### 4.7 Copiar el paquete a la Kria

Desde **PowerShell** (no desde WSL). Ajustar la ruta que devuelve `wslpath -w ~/Kria_Prjs/$NAME/${NAME}_pkg`:

```powershell
scp -r "\\wsl.localhost\Ubuntu-20.04\home\user1\Kria_Prjs\<NAME>\<NAME>_pkg" ubuntu@192.168.137.50:~/
```

Si WSL alcanzara la Kria desde otra red, el `scp` desde WSL serviría; en este montaje no.

---

## 5. Despliegue en la Kria

### 5.1 Variables en la Kria

En la terminal de la Kria (fuera del contenedor), con los valores del modelo (sección 2) y los de `mean/scale` (sección 4.5):

```bash
export NAME=ssd_mobilenet_v2_coco_tf
export AITASK=ssd_mobilenet_v2_coco
export MODEL_CLASS=TFSSD
export MEAN_R=0 MEAN_G=0 MEAN_B=0                 # reemplazar con los del prototxt
export SCALE_R=1 SCALE_G=1 SCALE_B=1              # reemplazar con scale_config
```

### 5.2 Archivos de configuración de VVAS

Tres JSON en `~/${AITASK}_vvas` (en el host; se montan dentro del contenedor). Los dos primeros usan las variables; el tercero se edita a mano.

```bash
mkdir -p ~/${AITASK}_vvas && cd ~/${AITASK}_vvas
cat > preprocess.json << EOF
{
  "xclbin-location":"/lib/firmware/xilinx/kv260-smartcam/kv260-smartcam.xclbin",
  "vvas-library-repo": "/opt/xilinx/kv260-smartcam/lib",
  "element-mode": "transform",
  "kernels": [
    {
      "kernel-name": "pp_pipeline_accel:{pp_pipeline_accel_1}",
      "library-name": "libvvas_xpp.so",
      "config": {
        "debug_level" : 1,
        "mean_r": $MEAN_R,
        "mean_g": $MEAN_G,
        "mean_b": $MEAN_B,
        "scale_r": $SCALE_R,
        "scale_g": $SCALE_G,
        "scale_b": $SCALE_B
      }
    }
  ]
}
EOF
cat > aiinference.json << EOF
{
 "xclbin-location":"/lib/firmware/xilinx/kv260-smartcam/kv260-smartcam.xclbin",
 "vvas-library-repo": "/usr/lib/aarch64-linux-gnu/",
 "element-mode":"inplace",
 "kernels" :[
   {
     "library-name":"libvvas_xdpuinfer.so",
     "config": {
       "model-name" : "$NAME",
       "model-class" : "$MODEL_CLASS",
       "model-path" : "/opt/xilinx/kv260-smartcam/share/vitis_ai_library/models",
       "run_time_model" : false,
       "need_preprocess" : false,
       "performance_test" : false,
       "debug_level" : 0
     }
   }
 ]
}
EOF
cat > drawresult.json << 'EOF'
{
  "xclbin-location":"/usr/lib/dpu.xclbin",
  "vvas-library-repo": "/opt/xilinx/kv260-smartcam/lib",
  "element-mode":"inplace",
  "kernels" :[
    {
      "library-name":"libvvas_airender.so",
      "config": {
        "fps_interval" : 10,
        "font_size" : 2,
        "font" : 3,
        "thickness" : 2,
        "debug_level" : 0,
        "label_color" : { "blue" : 0, "green" : 0, "red" : 255 },
        "label_filter" : [ "class", "probability" ],
        "classes" : [
          { "name" : "car", "blue" : 255, "green" : 0, "red" : 0 },
          { "name" : "person", "blue" : 0, "green" : 255, "red" : 0 },
          { "name" : "truck", "blue" : 128, "green" : 255, "red" : 0 },
          { "name" : "bicycle", "blue" : 0, "green" : 0, "red" : 255 }
        ]
      }
    }
  ]
}
EOF
cat preprocess.json | grep -E "mean|scale"; grep -E "model-" aiinference.json; ls -l
```

Reglas de `drawresult.json`:

- Solo se dibujan las clases listadas en `classes` (la guía oficial elige cuatro). Los nombres deben coincidir con los `name` del `label.json`, que **no son los mismos en todos los modelos**: YOLOv3 usa `motorbike`, el SSD de TensorFlow usa `motorcycle`.
- Para videovigilancia con SSD, añadir por ejemplo `bus`, `motorcycle`, `backpack`, `handbag` y `suitcase`.

El nombre del modelo (`$NAME`) debe coincidir exactamente en: carpeta del modelo, `.xmodel`, `.prototxt`, `label.json` y `model-name` de `aiinference.json`. El nombre `$AITASK` de la carpeta de configs es lo que se pasa a `-a` / `--aitask`.

### 5.3 Overlay (orden de la guía)

```bash
sudo xmutil desktop_disable; sudo xmutil unloadapp; sudo xmutil loadapp kv260-smartcam && sudo xmutil listapps
```

`desktop_disable` deja en negro el monitor conectado a la Kria; SSH y UART siguen funcionando. Al terminar todo: `sudo xmutil desktop_enable`.

### 5.4 Contenedor de smartcam

Es el comando de la guía de despliegue, más:

- `--env NAME --env AITASK`, para reutilizar las variables dentro del contenedor.
- Tres `-v`, para que el modelo, las configs y los videos vivan en el host y no se pierdan al borrar el contenedor.

```bash
docker run --env="DISPLAY" --env NAME --env AITASK -h "xlnx-docker" --env="XDG_SESSION_TYPE" --net=host --privileged --volume="$HOME/.Xauthority:/root/.Xauthority:rw" -v /tmp:/tmp -v /dev:/dev -v /sys:/sys -v /etc/vart.conf:/etc/vart.conf -v /lib/firmware/xilinx:/lib/firmware/xilinx -v /run:/run -v $HOME/videos:/videos -v $HOME/${NAME}_pkg:/opt/xilinx/kv260-smartcam/share/vitis_ai_library/models/${NAME} -v $HOME/${AITASK}_vvas:/opt/xilinx/kv260-smartcam/share/vvas/${AITASK} -it xilinx/smartcam:2022.1 bash
```

Verificar los montajes dentro del contenedor:

```bash
ls /videos /opt/xilinx/kv260-smartcam/share/vitis_ai_library/models/$NAME /opt/xilinx/kv260-smartcam/share/vvas/$AITASK
```

### 5.5 Ejecutar

```bash
smartcam --file /videos/alley.nv12.h264 -i h264 -W 1920 -H 1080 -r 30 --target rtsp -a $AITASK
```

En el arranque deben aparecer las líneas `Resize: scale_r=...` con los valores de `preprocess.json`: significa que se leyó la configuración. Si no aparecen, `-a` apunta a un nombre de carpeta que no existe.

Ver el stream desde la PC (un solo cliente a la vez):

```powershell
ffplay -rtsp_transport tcp rtsp://192.168.137.50:554/test
```

---

## 6. Videos de prueba

Las pruebas con archivo usan dos videos de la guía de despliegue, convertidos a H.264 crudo, que es el formato que espera `smartcam --file ... -i h264`.

### 6.1 Videos de origen

| Video | Página | Archivo descargado | Nombre en la Kria |
|---|---|---|---|
| `alley` (personas caminando) | https://pixabay.com/videos/alley-people-walk-street-ukraine-39837/ | `39837-424360872.mp4` | `~/videos/alley.mp4` |
| `freeway` (autopista bajo la lluvia) | https://pixabay.com/videos/freeway-traffic-cars-rainy-truck-8358/ | `8358-208052058.mp4` | `~/videos/freeway.mp4` |

Para videovigilancia, `alley` (personas) sirve para comprobar `person` y `freeway` (autos y camiones) para vehículos.

### 6.2 Descargar y copiar a la Kria

Pixabay bloquea las descargas con `wget` (`403 Forbidden`), así que se descargan en el navegador de la PC con el botón **Download**. Después se copian desde **PowerShell** (no desde WSL).

Crear la carpeta destino en la Kria:

```powershell
ssh ubuntu@192.168.137.50 "mkdir -p ~/videos"
```

Copiar (el `:~/videos/...` del destino es obligatorio; sin él `scp` copia el archivo en local):

```powershell
cd $env:USERPROFILE\Downloads
scp .\39837-424360872.mp4 ubuntu@192.168.137.50:~/videos/alley.mp4
scp .\8358-208052058.mp4 ubuntu@192.168.137.50:~/videos/freeway.mp4
```

Comprobar en la Kria:

```bash
cd ~/videos && ls -lh && file *.mp4
```

Cada archivo debe pesar varios MB y `file` debe decir `ISO Media, MP4`.

### 6.3 Transcodificar a H.264 (30 fps)

Es el comando de la guía: 1920x1080, formato de píxel NV12 y 30 fps. Se aplica a los dos videos (en la Kria):

```bash
cd ~/videos && for n in alley freeway; do ffmpeg -y -i $n.mp4 -c:v libx264 -pix_fmt nv12 -vf scale=1920:1080 -r 30 $n.nv12.h264; done && ls -lh *.h264
```

`scale=1920:1080` fuerza la proporción 16:9 y puede deformar un poco la imagen; para estas pruebas no importa.

### 6.4 Versión de 10 fps

Para la prueba con YOLOv3 (sección 8) se generó una copia de `alley` a 10 fps. Solo cambia `-r`:

```bash
cd ~/videos && ffmpeg -y -i alley.mp4 -c:v libx264 -pix_fmt nv12 -vf scale=1920:1080 -r 10 alley_10fps.nv12.h264 && ls -lh alley_10fps.nv12.h264
```

### 6.5 Parámetros de `smartcam` por archivo

`-W`, `-H` y `-r` describen el archivo de entrada y deben coincidir con él; si no, el pipeline falla con `not-negotiated`.

| Archivo | `-W` | `-H` | `-r` |
|---|---|---|---|
| `/videos/alley.nv12.h264` | 1920 | 1080 | 30 |
| `/videos/freeway.nv12.h264` | 1920 | 1080 | 30 |
| `/videos/alley_10fps.nv12.h264` | 1920 | 1080 | 10 |

---

## 7. Medir el rendimiento y decidir si cumple los 30 fps

Se mide por capas, de adentro hacia afuera, para saber **dónde** está el límite si algo falla.

### 7.1 Control del pipeline con un modelo integrado (una sola vez)

Antes de culpar al modelo nuevo, comprobar que el pipeline de la placa sostiene 30 fps con un modelo ligero que ya trae la imagen. Dentro del contenedor, con el video de 30 fps:

```bash
smartcam --file /videos/alley.nv12.h264 -i h264 -W 1920 -H 1080 -r 30 --target rtsp -a ssd
```

Medir desde la PC con el comando de 7.4. Si aquí ya no se llega a ≈30 fps y `speed≈1x`, el problema es del pipeline, la red o el cliente, no del modelo [por verificar en esta placa; con YOLOv3 no se pudo separar].

### 7.2 Solo el DPU: `xdputil benchmark`

Requiere `numpy` dentro del contenedor (si falta, `ModuleNotFoundError`):

```bash
apt update && apt install -y python3-numpy && python3 -c "import numpy; print(numpy.__version__)"
```

Con `smartcam` detenido:

```bash
M=/opt/xilinx/kv260-smartcam/share/vitis_ai_library/models/$NAME/$NAME.xmodel; for t in 1 2 4; do echo "=== threads: $t ==="; xdputil benchmark $M $t; done
```

Es el techo del modelo en este DPU. Si 1, 2 y 4 hilos dan casi lo mismo, el DPU ya está saturado (así pasó con YOLOv3).

### 7.3 Contador de `smartcam` (`performance_test`)

Activar el campo en `aiinference.json` (en el host, sin reiniciar el contenedor):

```bash
sed -i 's/"performance_test" : false/"performance_test" : true/' ~/${AITASK}_vvas/aiinference.json && grep performance_test ~/${AITASK}_vvas/aiinference.json
```

Al volver a lanzar `smartcam` aparece una línea nueva en la terminal:

```
frame=  569 fps= 9.535
```

Con una entrada de 30 fps este contador no puede superar ≈30: lo que interesa es que **se mantenga en ≈30 durante varios minutos**.

La opción `-R` ("Report fps" en la ayuda de `smartcam`) se probó y no mostró ninguna diferencia visible; no se sabe qué reporta ni dónde.

### 7.4 Desde la PC: lo que entrega el stream

Instalar FFplay/FFmpeg en Windows:

```powershell
winget install --id Gyan.FFmpeg -e
```

Recargar el PATH en la sesión actual (o reabrir toda la terminal):

```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User"); ffplay -version
```

Medir (decodifica y descarta, no reproduce):

```powershell
ffmpeg -rtsp_transport tcp -i rtsp://192.168.137.50:554/test -t 20 -an -f null -
```

Se lee en la última línea: `speed≈1.00x` y ≈30 fps significa que el stream avanza en tiempo real. Con YOLOv3 salió `speed=0.323x`. El comando con `-t` puede no terminar si el tiempo del stream no avanza (`Ctrl+C`).

Clientes: **VLC se traba, arranca bien y luego se detiene, y a veces no abre**. FFplay con `-rtsp_transport tcp` es algo más fluido (la guía oficial también avisa que VLC falla a veces).

### 7.5 Criterio de aceptación para 30 fps estables

| Prueba | Pasa si | Si falla |
|---|---|---|
| `xdputil benchmark` (7.2) | ≥45 fps | Pasar al siguiente modelo más ligero de la sección 3.2 |
| Contador de `smartcam` con video de 30 fps, ≥5 minutos (7.3) | ≈30 fps sostenido, sin caídas | `top` en la Kria: ¿CPU al 100 %? El post-proceso (NMS) y el dibujo corren en CPU. Subir `conf_threshold` en el prototxt o bajar el número de clases dibujadas |
| `ffmpeg` desde la PC (7.4) | `speed≈1.00x` | Cliente o red: usar FFplay con TCP y un solo cliente |
| Imagen en `ffplay` | Cajas sobre personas/vehículos con la etiqueta correcta | Índice de etiquetas corrido, mean/scale o orden de canales (sección 9.3) |

---

## 8. Caso 1: YOLOv3 COCO 416 (`yolov3_coco_416_tf2`) [verificado]

### 8.1 Resumen de resultados

| Tema | Resultado |
|---|---|
| Procedimiento | Igual al de la guía oficial, con `--options '{"input_shape": "1,416,416,3"}'` al compilar |
| Despliegue | El modelo carga y el stream RTSP se genera |
| Rendimiento | **≈10 fps**, medido por tres vías independientes |
| Cuello de botella | El DPU B3136 con este modelo: más hilos no mejoran los fps |
| Video de 30 fps | Se reproduce a ≈0.32x (cámara lenta), no se "atasca" |
| Video de 10 fps | Se reproduce bien |
| Cámara MIPI | Solo admite 1920x1080@30 o 3840x2160@30 |
| Cámara USB | Sin resolver (error OMX en la prueba sin inferencia) |

YOLOv3 es unas diez veces más pesado que los modelos podados que trae la guía oficial. Con 65.9 GOPs por cuadro y 10.2 fps, el DPU rinde ≈0.67 TOPS efectivos.

### 8.2 Mediciones

| Medición | fps |
|---|---|
| `ffmpeg` desde la PC (stream completo): 601 cuadros en 62 s, `speed=0.323x` | 9.7 |
| Contador de `smartcam` | 9.5 |
| `xdputil benchmark`, 1 hilo (611 cuadros en 60.06 s) | 10.17 |
| `xdputil benchmark`, 2 hilos | 10.27 |
| `xdputil benchmark`, 4 hilos | 10.27 |

El pipeline completo llega a más del 90 % del tope del modelo. Con el modelo corriendo a 10 fps, un reproductor que espera 30 fps vacía su búfer y parece atascado.

### 8.3 Pruebas y observaciones

- **Cámara MIPI + YOLOv3** (`smartcam --mipi -W 1920 -H 1080 -r 30 --target rtsp -a yolov3_coco`): el video se congelaba, luego quedaba negro y el ventilador aceleraba. La cámara MIPI solo admite 1080p@30 o 4K@30, así que no se puede bajar la carga con ella.
- **`-a` y los nombres:** con un nombre de carpeta inexistente (`yolov3`) no aparecen las líneas `Resize: scale_r=...`; con `yolov3_coco` sí.
- **Parámetros que no coinciden:** con `-W 640 -H 360 -r 10` sobre un archivo de 1080p30, `GST_DEBUG=3` mostró `omxh264dec ... reason not-negotiated` y `rtsp-client: no media`. El pipeline se arma cuando un cliente se conecta, por eso el error aparece al conectar.
- **Sin inferencia (`-n`) con archivo:** el stream entrega ≈36 fps pero el tiempo del video queda congelado (`speed=0.00154x`, imagen estática); la causa no se determinó.
- **Video a 10 fps** (`-r 10`, sección 6.4): salió bien. No se anotaron fps medidos ni si aparecían cajas.
- **Cámara USB sin inferencia** (`smartcam --usb 0 -W 640 -H 480 -r 30 --target rtsp -n`): `stream ready` y luego `OMX_ErrorIncorrectStateOperation`; el proceso siguió vivo. Descartado: el `dmesg` no mostró errores del VCU y la memoria CMA estaba sana (732 MB libres de 800 MB). Modos reportados: 640x480, 640x360, 320x240 y 176x144, todos a 30 fps. **Pendiente:** repetir con la MIPI sin inferencia como control, y luego la USB con `GST_DEBUG=3` y el modo 640x360.
- **Aborto puntual:** en una corrida con YOLOv3 sobre archivo, `smartcam` abortó una vez con `module/module_dec.cpp:440: void DecModule::FreeDMA(int): Assertion '!handles.Exist(handle)' failed` (aserción del módulo del decodificador del VCU). No se debe a la opción `-R`. No se volvió a reproducir y no se anotó qué cliente RTSP estaba conectado.

### 8.4 Comparación con las guías oficiales

El procedimiento no tuvo desviaciones relevantes: modelo, `arch.json`, prototxt, `label.json` y `scale` iguales; compilación igual salvo `--options`; `preprocess.json` y `aiinference.json` equivalentes. El `drawresult.json` de `ssd` dibuja 3 clases y el de la guía de YOLOv3 añade `truck`.

---

## 9. Caso 2: SSD-MobileNetV2 COCO 300 para videovigilancia a 30 fps [por verificar]

### 9.1 Qué se va a probar

Que `ssd_mobilenet_v2_coco_tf` corra en smartcam con una entrada de 30 fps de forma estable (criterio de la sección 7.5) y detecte personas y vehículos en `alley` y `freeway`.

### 9.2 Valores esperados

| Variable | Valor |
|---|---|
| `ZOO_ID` | `tf_ssdmobilenetv2_coco_300_300_3.75G_2.5` |
| `NAME` | `ssd_mobilenet_v2_coco_tf` (confirmar en el `model.yaml`) |
| `AITASK` | `ssd_mobilenet_v2_coco` |
| `MODEL_CLASS` | `TFSSD` |
| Compilación | `vai_c_tensorflow` con `quantize_eval_model.pb` |
| Estimación del DPU | ≈61 fps (1 hilo), ≈79 fps (multihilo) |

### 9.3 Pasos (con el orden de la guía)

1. **Control del pipeline** con `-a ssd` (7.1).
2. **Preparar el modelo** (4.1 a 4.4): descargar con `ZOO_ID` del caso 2 y compilar con `vai_c_tensorflow`.
3. **Calcular `mean/scale`** (4.5): leer el prototxt y el fixpos; comprobar la regla de cordura.
4. **`label.json`** (4.6) con el diccionario COCO de 91 posiciones (Anexo A).
5. **Paquete y copia** a la Kria (4.6 y 4.7).
6. **Configs, overlay y contenedor** (5.1 a 5.5), con `drawresult.json` ampliado a las clases de vigilancia.
7. **Medir** `xdputil benchmark` primero (7.2): si da menos de 45 fps, no seguir y pasar a `ssdlite_mobilenet_v2_coco_tf`.
8. **Medir el pipeline** con el video de 30 fps (7.3 y 7.4) y mirar la imagen.

### 9.4 Riesgos conocidos

Todo esto sale de la documentación y está sin probar en la placa:

| Riesgo | Cómo comprobarlo |
|---|---|
| La imagen `smartcam:2022.1` podría no incluir la clase `TFSSD` | Al arrancar, un error de `model-class` no soportado en el log. Alternativa: `RAWTENSOR` (sin cajas) o cambiar a un modelo con clase soportada |
| El `mean` de los SSD de TF suele ser fraccionario (p. ej. 127.5) y el kernel de preprocesado podría redondearlo | Comparar detecciones con 127 y 128 si la precisión se ve baja |
| Orden de canales: el ejemplo de VVAS 3.0 con este modelo declara `"model-format": "RGB"`, y el `aiinference.json` de smartcam no tiene ese campo | Si hay cajas pero las clases son malas, probar añadir `"model-format": "RGB"` o `"BGR"` |
| Índice de etiquetas desplazado (91 posiciones frente a 80 de YOLO) | Mirar que `alley` marque `person` y no `bicycle` |
| Post-proceso del SSD (NMS sobre 1917 anclas) en la CPU | `top` durante la prueba de 30 fps |
| Entrada de 300×300: objetos pequeños se pierden en 1080p | Es un límite del modelo, no de la configuración |

### 9.5 Resultados (llenar al probar)

| Medición | Resultado | Fecha |
|---|---|---|
| `NAME` real en el `model.yaml` | | |
| Fixpos de entrada, `mean` y `scale_config` | | |
| Control `-a ssd`: fps y `speed` desde la PC | | |
| `xdputil benchmark`, 1 / 2 / 4 hilos | | |
| Contador de `smartcam`, 30 fps, 5 min | | |
| `ffmpeg` desde la PC: fps y `speed` | | |
| ¿Cajas y etiquetas correctas en `alley` y `freeway`? | | |
| `top`: CPU durante la prueba | | |

---

## 10. Problemas encontrados y soluciones

| Síntoma | Causa | Solución |
|---|---|---|
| `conda: command not found` en WSL | Se corrió fuera del contenedor de Vitis AI | Lanzar `vitis-ai-cpu:2.5.0` y activar el entorno que toque (4.4) dentro |
| Compilación: `Invalid shape of input layer: [1, None, None, 3]` | El `quantized.h5` tiene entrada dinámica | Añadir `--options '{"input_shape": "1,H,W,3"}'` |
| Ruta del `quantized.h5` no encontrada | Se usó la ruta de la versión 3.5 | Usar la del zip 2.5 (4.2) |
| `scp` desde WSL: `Network is unreachable` | WSL2 está en otra red virtual | Hacer el `scp` desde PowerShell |
| `scp` "rapidísimo" y sin pedir contraseña | Falta `:ruta` en el destino; copió localmente a un archivo llamado `ubuntu@192.168.137.50` | `scp archivo ubuntu@192.168.137.50:~/carpeta/` y borrar el archivo sobrante |
| `wget` de Pixabay: `403 Forbidden` (con `-O` queda un archivo de 0 bytes) | Protección de Cloudflare | Descargar en el navegador y pasar por `scp` |
| `ffmpeg`: `moov atom not found` | El archivo estaba vacío (0 bytes) | Borrarlo y copiar el video bien |
| `PermissionError` al editar los JSON | Los copió el contenedor como `root` | `sudo chown -R ubuntu:ubuntu ~/${AITASK}_vvas` |
| `Unknown option --AItask` | La opción real es `--aitask` (en minúsculas); la guía tiene el typo | Usar `--aitask` o `-a` |
| `stream ready` pero VLC no abre; log con `not-negotiated` | `-W -H -r` no coinciden con el archivo | Usar los valores reales del archivo |
| `MIPI src resolution can only be 1080p/4K` | Limitación de la cámara MIPI en `smartcam` | Usar 1920x1080@30 o 3840x2160@30, o la cámara USB / archivos |
| Video lento o "atascado" con un modelo | El modelo da menos fps que el video | Medir con 7.2; usar un video a la tasa del modelo, un modelo más ligero (sección 3.2) o menor resolución de entrada |
| `ffplay` no se reconoce tras `winget install` | La sesión tiene el PATH anterior | Recargar el PATH o reabrir toda la terminal |
| `xdputil benchmark`: `No module named 'numpy'` | Falta en la imagen | `apt update && apt install -y python3-numpy` |
| `smartcam` abortado con `FreeDMA` (una vez) | No determinada; no está relacionado con `-R` | Volver a lanzar; si se repite, cerrar clientes, `docker stop $(docker ps -q)` y reiniciar la tarjeta |

---

## 11. Siguientes pasos

1. Correr el control `-a ssd` con el video de 30 fps (7.1) y anotar fps y `speed`.
2. Seguir el caso 2 (sección 9) y llenar la tabla 9.5. Pasar cada [por verificar] que se confirme a [verificado], y corregir la guía donde la realidad difiera (comando de compilación TF 1, `NAME`, `model-class`, orden de canales y etiquetas).
3. Si SSD-MobileNetV2 no llega al criterio, repetir con `ssdlite_mobilenet_v2_coco_tf` (mismo procedimiento, cambian solo las variables).
4. Anotar si aparecen cajas sobre las personas en la prueba de 10 fps con YOLOv3.
5. Resolver la cámara USB (8.3).
6. Limpieza al terminar:

   ```bash
   sudo xmutil desktop_enable
   ```

   y poner `"performance_test" : false` en `aiinference.json`.

---

## 12. Referencia rápida

**Un modelo nuevo = cinco cosas que cambian**

1. El **xmodel compilado** para B3136 (4.4).
2. El **prototxt** del paquete de kv260 (4.2).
3. El **`label.json`** (4.6).
4. **`mean/scale`** en `preprocess.json` y **`model-class`** y `model-name` en `aiinference.json` (4.5 y 5.2).
5. El nombre de la carpeta de configs, que es lo que va en **`-a`** (5.2).

**Reglas que conviene recordar**

- La guía solo soporta Vitis AI 2.5.0: compilar con `vitis-ai-cpu:2.5.0` y usar modelos de la versión 2.5. Un xmodel compilado con otra versión da segfault.
- Nunca usar el `.xmodel` del `.tar.gz` de kv260: está compilado para otro DPU. Se compila el modelo cuantizado del zip GPU.
- El overlay (`xmutil loadapp kv260-smartcam`) se carga **antes** de lanzar el contenedor.
- Un cliente RTSP a la vez; cada conexión crea su propio pipeline.
- `smartcam` debe estar detenido (`Ctrl+C`) antes de lanzar otra instancia o de correr `xdputil benchmark`.
- Con entrada por archivo, `-W -H -r` deben coincidir con el archivo.
- Para 30 fps estables: ≥45 fps en `xdputil benchmark`.

**Ubicaciones dentro del contenedor `smartcam`**

| Qué | Ruta |
|---|---|
| Modelo (xmodel, prototxt, label.json) | `/opt/xilinx/kv260-smartcam/share/vitis_ai_library/models/$NAME/` |
| Configs de VVAS | `/opt/xilinx/kv260-smartcam/share/vvas/$AITASK/` |
| Videos | `/videos/` |

**Ubicaciones en el host de la Kria**

| Qué | Ruta |
|---|---|
| Paquete del modelo | `~/${NAME}_pkg/` |
| Configs de VVAS | `~/${AITASK}_vvas/` |
| Videos | `~/videos/` |

---

## Anexo A. Listas de etiquetas para `label.json`

Pegar el diccionario correspondiente en `names_by_index` del script de la sección 4.6.

**YOLOv3 COCO (80 clases, índice desde 0)** [verificado]

```python
names = ["person","bicycle","car","motorbike","aeroplane","bus","train","truck","boat","traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat","dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack","umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball","kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket","bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple","sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair","sofa","pottedplant","bed","diningtable","toilet","tvmonitor","laptop","mouse","remote","keyboard","cell phone","microwave","oven","toaster","sink","refrigerator","book","clock","vase","scissors","teddy bear","hair drier","toothbrush"]
assert len(names) == 80
names_by_index = dict(enumerate(names))
```

**SSD de TensorFlow sobre COCO (identificadores de categoría de COCO, 91 posiciones)** [por verificar el índice]

```python
names_by_index = {1:"person",2:"bicycle",3:"car",4:"motorcycle",5:"airplane",6:"bus",7:"train",8:"truck",9:"boat",10:"traffic light",11:"fire hydrant",13:"stop sign",14:"parking meter",15:"bench",16:"bird",17:"cat",18:"dog",19:"horse",20:"sheep",21:"cow",22:"elephant",23:"bear",24:"zebra",25:"giraffe",27:"backpack",28:"umbrella",31:"handbag",32:"tie",33:"suitcase",34:"frisbee",35:"skis",36:"snowboard",37:"sports ball",38:"kite",39:"baseball bat",40:"baseball glove",41:"skateboard",42:"surfboard",43:"tennis racket",44:"bottle",46:"wine glass",47:"cup",48:"fork",49:"knife",50:"spoon",51:"bowl",52:"banana",53:"apple",54:"sandwich",55:"orange",56:"broccoli",57:"carrot",58:"hot dog",59:"pizza",60:"donut",61:"cake",62:"chair",63:"couch",64:"potted plant",65:"bed",67:"dining table",70:"toilet",72:"tv",73:"laptop",74:"mouse",75:"remote",76:"keyboard",77:"cell phone",78:"microwave",79:"oven",80:"toaster",81:"sink",82:"refrigerator",84:"book",85:"clock",86:"vase",87:"scissors",88:"teddy bear",89:"hair drier",90:"toothbrush"}
assert len(names_by_index) == 80
```

Si en pantalla las etiquetas salen corridas una posición, desplazar las claves (`{k-1: v ...}` o `{k+1: v ...}`) y regenerar el `label.json`.
