# ADR 0002 — Privilegios con pkexec, un prompt por operación, sin shell

- Estado: aceptado (reemplaza la versión inicial con `shell=True`)

## Contexto
Se necesita root para `loginctl attach`, `flush-devices` y `systemctl enable/disable`. La versión inicial construía strings de shell (`f"loginctl attach {seat} {path}"`) y lanzaba un `pkexec` por comando: rutas con espacios/metacaracteres rompían o inyectaban, y aplicar un preset pedía la contraseña N veces.

## Decisión
- `run_cmd` ejecuta listas argv, nunca `shell=True`.
- Operaciones por lotes usan `run_root_script(script, *args)` → `pkexec sh -c script sh args…` con los datos como `"$@"`.
- No se ejecuta la app completa como root (GTK como root es mala práctica).

## Consecuencias
+ Seguro frente a rutas arbitrarias; un solo diálogo polkit por acción.
− Los scripts sh deben ser POSIX y mantenerse pequeños.
