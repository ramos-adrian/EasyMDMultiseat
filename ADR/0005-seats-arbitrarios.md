# ADR 0005 — Seats arbitrarios (`seatN`)

- Estado: aceptado

## Contexto
La primera versión solo conocía `seat0` y `seat1` (columna fija en la GUI, `"seat1"` incrustado en CLI y presets).

## Decisión
- Cualquier nombre que cumpla `^seat[A-Za-z0-9_-]+$` es válido (`core.is_valid_seat`); se valida antes de llamar a `loginctl` y antes de pasarlo al script de root.
- La GUI muestra seat0 a la izquierda y, a la derecha, un desplegable con los seats existentes (`loginctl list-seats`) más un botón «+» que propone el siguiente libre (`next_seat_name`). La CLI pregunta el seat destino (Enter = seat1, `new` = siguiente libre).
- Los presets guardan su seat (`{"seat","devices"}`); los antiguos se leen como seat1.

## Consecuencias
+ N puestos. − logind no lista seats sin dispositivos, así que un seat recién creado en la UI es «virtual» hasta que se le asigna algo.

## Adenda — asignación en dos pasos
Mover un dispositivo ya no modifica el sistema: la GUI lo marca como pendiente (`pending`, mostrado con «●» y botón «Deshacer») y una barra inferior ofrece «Aplicar cambios» / «Descartar». Al aplicar, `core.apply_seat_assignments` envía todos los movimientos (de cualquier seat) en un solo `pkexec`, colapsando sub-dispositivos a su ancestro (`collapse_assignments`). La CLI sigue el mismo flujo (número = marcar, `a` = aplicar, `c` = limpiar). Los perfiles conservan su propio diálogo de confirmación.
