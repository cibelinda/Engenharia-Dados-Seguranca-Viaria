"""Download reproduzível dos arquivos da PRF listados em sources.yaml.

Uso:
    python -m blackspot.download                    # baixa o que falta e verifica
    python -m blackspot.download --system bat --year 2024
    python -m blackspot.download --verify-only      # só confere os arquivos locais
    python -m blackspot.download --accept-new-hash bat_2024_pessoa

Checksums: cada entrada do manifesto tem um sha256 de referência. A PRF regrava
arquivos no mesmo ID/nome, então uma divergência NÃO interrompe a execução:
o arquivo é mantido, um aviso explícito é emitido e o evento fica registrado em
<dest>/_download_report.json. A referência só muda com --accept-new-hash KEY ou
--accept-all-new-hashes. Com --strict, divergências fazem o processo sair com
código 2 (útil em CI).

Códigos de saída: 0 = ok (com ou sem avisos), 1 = falha de download/arquivo
inválido, 2 = divergência de hash com --strict.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "sources.yaml"
DEFAULT_DEST = REPO_ROOT / "data" / "raw"
REPORT_NAME = "_download_report.json"

CHUNK = 1 << 20
RETRIES = 3
TIMEOUT_S = 120
USER_AGENT = "blackspot-downloader/0.1 (+BD2 FCTE/UnB)"


@dataclass
class Result:
    key: str
    filename: str
    status: str  # ok | downloaded | hash_mismatch | error
    source: str  # cache | remote | none
    expected_sha256: str | None
    observed_sha256: str | None = None
    size_bytes: int | None = None
    drive_last_modified: str | None = None
    message: str = ""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    keys = [e["key"] for e in manifest["files"]]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise SystemExit(f"sources.yaml: chaves duplicadas: {sorted(dupes)}")
    return manifest


def select(entries: list[dict], args: argparse.Namespace) -> list[dict]:
    out = entries
    if args.key:
        unknown = set(args.key) - {e["key"] for e in entries}
        if unknown:
            raise SystemExit(f"chave(s) inexistente(s) no manifesto: {sorted(unknown)}")
        out = [e for e in out if e["key"] in args.key]
    if args.system:
        out = [e for e in out if e["system"] in args.system]
    if args.dataset:
        out = [e for e in out if e["dataset"] in args.dataset]
    if args.year:
        out = [e for e in out if e["year"] in args.year]
    return out


def fetch(url: str, dest: Path) -> str | None:
    """Baixa `url` para `dest` de forma atômica. Retorna o Last-Modified remoto."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                ctype = resp.headers.get("Content-Type", "")
                if ctype.startswith("text/html"):
                    # O Drive responde HTML quando o arquivo some, muda de
                    # permissão ou estoura cota — nunca é o ZIP esperado.
                    raise RuntimeError(
                        f"Drive respondeu HTML em vez do arquivo (Content-Type={ctype}); "
                        "o ID pode ter sido removido ou tornado privado"
                    )
                last_modified = resp.headers.get("Last-Modified")
                with tmp.open("wb") as f:
                    while chunk := resp.read(CHUNK):
                        f.write(chunk)
            if not zipfile.is_zipfile(tmp):
                raise RuntimeError("conteúdo baixado não é um ZIP válido")
            tmp.replace(dest)
            if last_modified:
                return parsedate_to_datetime(last_modified).strftime("%Y-%m-%dT%H:%M:%SZ")
            return None
        # OSError cobre URLError, TimeoutError, ConnectionError e erros de disco;
        # HTTPException cobre IncompleteRead (conexão cortada no meio do corpo).
        except (OSError, http.client.HTTPException, RuntimeError) as e:
            last_err = e
            tmp.unlink(missing_ok=True)
            if isinstance(e, RuntimeError) or attempt == RETRIES:
                break
            time.sleep(2**attempt)
    raise RuntimeError(str(last_err))


def process(entry: dict, url_template: str, dest_dir: Path, force: bool, verify_only: bool) -> Result:
    key, filename = entry["key"], entry["filename"]
    expected = (entry.get("reference") or {}).get("sha256")
    expected = str(expected) if expected is not None else None
    path = dest_dir / filename
    res = Result(key=key, filename=filename, status="error", source="none", expected_sha256=expected)

    if path.exists() and not force:
        res.source = "cache"
    elif verify_only:
        res.message = "arquivo ausente (--verify-only não baixa)"
        return res
    else:
        try:
            res.drive_last_modified = fetch(url_template.format(drive_id=entry["drive_id"]), path)
            res.source = "remote"
        except RuntimeError as e:
            res.message = f"falha no download: {e}"
            return res

    res.observed_sha256 = sha256_of(path)
    res.size_bytes = path.stat().st_size
    if expected and res.observed_sha256 == expected:
        res.status = "ok" if res.source == "cache" else "downloaded"
    else:
        res.status = "hash_mismatch"
    return res


def warn_mismatch(r: Result) -> None:
    if r.source == "remote":
        cause = (
            "O arquivo acabou de ser baixado da PRF e difere da referência: provavelmente\n"
            "    foi REPUBLICADO pela PRF no mesmo ID/nome (revisão de dados)."
        )
    else:
        cause = (
            "O arquivo LOCAL difere da referência. Pode ser uma cópia antiga/corrompida\n"
            "    (rode com --force --key {k} para rebaixar) ou uma versão republicada já aceita."
        ).format(k=r.key)
    log(
        f"\n  AVISO: sha256 divergente em {r.key} ({r.filename})\n"
        f"    esperado: {r.expected_sha256}\n"
        f"    obtido:   {r.observed_sha256}  ({r.size_bytes} bytes"
        + (f", Drive last-modified {r.drive_last_modified}" if r.drive_last_modified else "")
        + f")\n    {cause}\n"
        f"    O arquivo foi mantido e o pipeline segue. Para adotar a nova versão como\n"
        f"    referência: python -m blackspot.download --accept-new-hash {r.key}\n"
    )


def update_reference(text: str, r: Result, today: str) -> str:
    """Reescreve o bloco `reference` de uma entrada preservando o resto do YAML."""
    start = re.search(rf"^  - key: {re.escape(r.key)}\n", text, re.M)
    if not start:
        raise RuntimeError(f"entrada {r.key} não encontrada no manifesto")
    nxt = re.compile(r"^  - key: ", re.M).search(text, start.end())
    end = nxt.start() if nxt else len(text)
    block = text[start.start():end]
    subs = {
        "sha256": f'"{r.observed_sha256}"',
        "size_bytes": r.size_bytes,
        # Arquivo vindo do cache não traz Last-Modified; manter o valor antigo
        # atribuiria a data da versão anterior ao novo sha256.
        "drive_last_modified": f'"{r.drive_last_modified}"' if r.drive_last_modified else "null",
        "verified_at": f'"{today}"',
    }
    for field, value in subs.items():
        block, n = re.subn(rf"^(      {field}: ).*$", rf"\g<1>{value}", block, count=1, flags=re.M)
        if n != 1:
            raise RuntimeError(f"campo reference.{field} não encontrado em {r.key}")
    return text[:start.start()] + block + text[end:]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    # Caminho relativo em BLACKSPOT_RAW_DIR é relativo à raiz do repositório, não ao cwd.
    p.add_argument("--dest", type=Path, default=REPO_ROOT / os.environ.get("BLACKSPOT_RAW_DIR", DEFAULT_DEST))
    p.add_argument("--key", action="append", help="baixa só esta entrada (repetível)")
    p.add_argument("--system", action="append", choices=["br_brasil", "bat"])
    p.add_argument("--dataset", action="append", choices=["ocorrencia", "pessoa", "pessoa_todas_causas"])
    p.add_argument("--year", action="append", type=int)
    p.add_argument("--jobs", type=int, default=int(os.environ.get("BLACKSPOT_DOWNLOAD_JOBS", 4)))
    p.add_argument("--force", action="store_true", help="rebaixa mesmo se o arquivo já existir")
    p.add_argument("--verify-only", action="store_true", help="não baixa; só confere arquivos locais")
    p.add_argument("--accept-new-hash", action="append", default=[], metavar="KEY",
                   help="grava o sha256 observado como nova referência para KEY (repetível)")
    p.add_argument("--accept-all-new-hashes", action="store_true")
    p.add_argument("--strict", action="store_true", help="sai com código 2 se houver divergência de hash")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = load_manifest(args.manifest)
    url_template = manifest["download"]["url_template"]
    # Aceitar um hash implica olhar para essa entrada, mesmo sem filtro explícito.
    if args.accept_new_hash and not (args.key or args.system or args.dataset or args.year):
        args.key = list(args.accept_new_hash)
    entries = select(manifest["files"], args)
    if not entries:
        log("nenhuma entrada do manifesto corresponde aos filtros")
        return 1
    args.dest.mkdir(parents=True, exist_ok=True)

    log(f"{len(entries)} arquivo(s) de {args.manifest.name} -> {args.dest}")
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        results = list(ex.map(
            lambda e: process(e, url_template, args.dest, args.force, args.verify_only), entries))

    for r in results:
        detail = r.message or (r.observed_sha256 or "")[:16]
        log(f"  {r.status:<14} {r.source:<6} {r.key:<36} {detail}")
    mismatches = [r for r in results if r.status == "hash_mismatch"]
    errors = [r for r in results if r.status == "error"]
    for r in mismatches:
        warn_mismatch(r)

    accepted: list[str] = []
    to_accept = {r.key for r in mismatches} if args.accept_all_new_hashes else set(args.accept_new_hash)
    if to_accept:
        text = args.manifest.read_text(encoding="utf-8")
        today = dt.date.today().isoformat()
        for r in mismatches:
            if r.key in to_accept:
                text = update_reference(text, r, today)
                accepted.append(r.key)
        args.manifest.write_text(text, encoding="utf-8")
        for k in sorted(to_accept - set(accepted)):
            log(f"  --accept-new-hash {k}: nada a aceitar (hash já confere ou arquivo indisponível)")
        for k in accepted:
            log(f"  referência atualizada em {args.manifest.name}: {k}")

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manifest": str(args.manifest),
        "accepted_new_hashes": accepted,
        "results": [asdict(r) for r in results],
    }
    (args.dest / REPORT_NAME).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")

    pending = [r for r in mismatches if r.key not in accepted]
    log(f"\nresumo: {len(results) - len(mismatches) - len(errors)} ok, "
        f"{len(pending)} divergente(s) pendente(s), {len(accepted)} aceito(s), {len(errors)} erro(s). "
        f"Relatório: {args.dest / REPORT_NAME}")
    if errors:
        return 1
    if pending and args.strict:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
