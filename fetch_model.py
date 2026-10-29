#!/usr/bin/env python3
"""Paso 1 - Descarga y prepara un modelo del Model Zoo 2.5.

Corre en el HOST (WSL). Lee el model.yaml del repo Vitis-AI (tag v2.5),
descarga el zip GPU y el tar.gz de kv260, verifica el md5, los extrae y
escribe model.env en la carpeta del modelo.

Uso:
    python3 fetch_model.py <ZOO_ID> [--repo ~/Vitis-AI] [--workdir ~/Kria_Prjs]
Ejemplo:
    python3 fetch_model.py tf_ssdmobilenetv2_coco_300_300_3.75G_2.5
"""
import argparse, glob, hashlib, os, re, subprocess, sys, tarfile, zipfile

BOARD_GPU = "GPU"
BOARD_KV260 = "zcu102 & zcu104 & kv260"
# Archivo cuantizado que se compila, segun el framework (prefijo del ZOO_ID)
QUANT = {
    "tf2": "quantized/quantized.h5",
    "tf": "quantized/quantize_eval_model.pb",
    "pt": "quantized/*_int.xmodel",
}


def die(msg):
    print("ERROR:", msg, file=sys.stderr)
    sys.exit(1)


def parse_model_yaml(path):
    """Devuelve (claves de nivel superior, lista de entradas de 'files')."""
    top, files, cur, in_files = {}, [], None, False
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("files:"):
            in_files = True
            continue
        if in_files and not line[0].isspace() and not line.startswith("- "):
            in_files = False
        m = re.match(r"^\s*(?:- )?([^:]+?):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1).strip(), m.group(2).strip().strip("'\"")
        if in_files:
            if line.lstrip().startswith("- "):
                cur = {}
                files.append(cur)
            if cur is not None:
                cur[key] = val
        else:
            top[key] = val
    return top, files


def pick(files, board):
    hits = [f for f in files if f.get("board") == board]
    if len(hits) != 1:
        die(f"se esperaba 1 entrada con board '{board}' en el model.yaml y hay {len(hits)}")
    return hits[0]


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, dest, checksum):
    if os.path.exists(dest) and md5(dest) == checksum:
        print(f"  ya descargado y verificado: {os.path.basename(dest)}")
        return
    tmp = dest + ".part"
    print(f"  descargando {os.path.basename(dest)}")
    if subprocess.call(["wget", "-q", "--show-progress", "-O", tmp, url]) != 0:
        die(f"fallo la descarga de {url}")
    if md5(tmp) != checksum:
        os.remove(tmp)
        die(f"el md5 no coincide en {os.path.basename(dest)}")
    os.replace(tmp, dest)
    print("  md5 OK")


def extract(archive, expected_dir):
    if os.path.isdir(expected_dir):
        print(f"  ya extraido: {expected_dir}/")
        return
    print(f"  extrayendo {os.path.basename(archive)}")
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(".")
    else:
        with tarfile.open(archive) as t:
            t.extractall(".")
    if not os.path.isdir(expected_dir):
        die(f"despues de extraer no existe la carpeta {expected_dir}/")


def update_env(path, new):
    env = {}
    if os.path.exists(path):
        for l in open(path):
            if "=" in l and not l.startswith("#"):
                k, v = l.rstrip("\n").split("=", 1)
                env[k] = v
    env.update(new)
    with open(path, "w") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zoo_id", help="carpeta en model_zoo/model-list/, p. ej. tf_ssdmobilenetv2_coco_300_300_3.75G_2.5")
    ap.add_argument("--repo", default="~/Vitis-AI", help="repo Vitis-AI en el tag v2.5 (default: ~/Vitis-AI)")
    ap.add_argument("--workdir", default="~/Kria_Prjs", help="carpeta base de trabajo (default: ~/Kria_Prjs)")
    a = ap.parse_args()

    repo, workdir = os.path.expanduser(a.repo), os.path.expanduser(a.workdir)
    yaml_path = os.path.join(repo, "model_zoo", "model-list", a.zoo_id, "model.yaml")
    if not os.path.isfile(yaml_path):
        die(f"no existe {yaml_path}\n"
            "  Clona el repo en el tag v2.5:\n"
            "  git clone --depth 1 --branch v2.5 https://github.com/Xilinx/Vitis-AI ~/Vitis-AI")
    top, files = parse_model_yaml(yaml_path)
    if top.get("version") != "2.5":
        die(f"el model.yaml dice version '{top.get('version')}', no 2.5: el repo no esta en el tag v2.5")

    prefix = a.zoo_id.split("_")[0]
    if prefix not in QUANT:
        die(f"prefijo '{prefix}' no soportado (se esperaba tf2, tf o pt)")

    gpu, kv = pick(files, BOARD_GPU), pick(files, BOARD_KV260)
    model = kv["name"]
    mdir = os.path.join(workdir, model)
    os.makedirs(mdir, exist_ok=True)
    os.chdir(mdir)
    print(f"Modelo: {model}   ({a.zoo_id}, framework {prefix})")
    print(f"Carpeta: {mdir}")

    print("Zip GPU (modelo float y cuantizado):")
    fetch(gpu["download link"], f"{a.zoo_id}.zip", gpu["checksum"])
    extract(f"{a.zoo_id}.zip", a.zoo_id)
    print("Tar.gz kv260 (solo se usan los .prototxt):")
    fetch(kv["download link"], f"{model}-kv260.tar.gz", kv["checksum"])
    extract(f"{model}-kv260.tar.gz", model)

    hits = glob.glob(os.path.join(a.zoo_id, QUANT[prefix]))
    if len(hits) != 1:
        die(f"se esperaba 1 archivo '{QUANT[prefix]}' en {a.zoo_id}/ y hay {len(hits)}")
    quant = os.path.relpath(hits[0])
    protos = sorted(glob.glob(os.path.join(model, "*.prototxt")))

    update_env("model.env", {
        "KV_ZOO_ID": a.zoo_id,
        "KV_MODEL": model,
        "KV_FRAMEWORK": prefix,
        "KV_QUANT_FILE": quant,
    })
    print("\nListo.")
    print(f"  A compilar:  {quant}")
    print("  Prototxt del paquete kv260:")
    for p in protos:
        print(f"    {p}")
    print(f"  model.env escrito en {mdir}/")
    print(f"\nPara cargar las variables en tu terminal:\n  cd {mdir} && set -a; . ./model.env; set +a")


if __name__ == "__main__":
    main()