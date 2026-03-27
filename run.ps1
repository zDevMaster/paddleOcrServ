param(
    [string]$Host = "0.0.0.0",
    [int]$Port = 8000
)

$env:OCR_BIND = "$Host`:$Port"
python -m gunicorn -c gunicorn_conf.py app.main:app

