FROM langgenius/dify-sandbox:0.2.14

USER root

RUN mkdir -p /usr/local/bin \
    && printf '%s\n' '#!/bin/sh' 'exec /opt/python/bin/python3 "$@"' > /usr/local/bin/python3 \
    && chmod +x /usr/local/bin/python3 \
    && /usr/local/bin/python3 -c "import json, sys; print(sys.executable)"

USER sandbox
