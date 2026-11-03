#!/usr/bin/env bash
# Uso: scripts/with-spinner.sh "mensaje" comando [args…]
#
# Corre el comando con su salida guardada en un fichero temporal y muestra un
# spinner con el tiempo transcurrido mientras tarda. Si falla, enseña lo que
# sacó. Sin terminal (CI, redirecciones) no hay spinner: el mensaje y, tal cual,
# la salida del comando.
set -u

msg=$1
shift

if [ ! -t 2 ]; then
	echo "$msg…" >&2
	exec "$@"
fi

log=$(mktemp)
"$@" >"$log" 2>&1 &
pid=$!
# Ctrl-C: parar el comando y no dejar el fichero temporal.
trap 'kill "$pid" 2>/dev/null; rm -f "$log"; printf "\r\033[K" >&2; exit 130' INT TERM

frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
start=$SECONDS
i=0
while kill -0 "$pid" 2>/dev/null; do
	printf '\r\033[K%s %s (%ds)' "${frames:i%10:1}" "$msg" $((SECONDS - start)) >&2
	i=$((i + 1))
	sleep 0.1
done
wait "$pid"
rc=$?
printf '\r\033[K' >&2

if [ "$rc" -eq 0 ]; then
	echo "✔ $msg ($((SECONDS - start))s)" >&2
else
	echo "✘ $msg" >&2
	cat "$log" >&2
fi
rm -f "$log"
exit "$rc"
