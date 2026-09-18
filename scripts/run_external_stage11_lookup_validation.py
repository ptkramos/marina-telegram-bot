"""External handoff for the v3.6.4 Brazilian holidays/place lookup supplement."""

from pathlib import Path

from run_external_stage11_validation import main


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    raise SystemExit(main(
        result_path=root / 'data' / 'real_world_lookup_validation.v364.json',
        supplement='real_world_lookup_feriados_br',
    ))
