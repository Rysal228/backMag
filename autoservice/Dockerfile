FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY certificates/*.cer /usr/local/share/ca-certificates/

RUN cp /usr/local/share/ca-certificates/Russian_Trusted_Root_CA.cer /usr/local/share/ca-certificates/Russian_Trusted_Root_CA.crt \
    && cp /usr/local/share/ca-certificates/Russian_Trusted_Sub_CA.cer /usr/local/share/ca-certificates/Russian_Trusted_Sub_CA.crt \
    && cp /usr/local/share/ca-certificates/Russian_Trusted_Sub_CA_2024.cer /usr/local/share/ca-certificates/Russian_Trusted_Sub_CA_2024.crt \
    && update-ca-certificates \
    && cat "$(python -c 'import certifi; print(certifi.where())')" \
        /usr/local/share/ca-certificates/Russian_Trusted_Root_CA.crt \
        /usr/local/share/ca-certificates/Russian_Trusted_Sub_CA.crt \
        /usr/local/share/ca-certificates/Russian_Trusted_Sub_CA_2024.crt \
        > /etc/ssl/certs/service-car-ca-bundle.pem

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/service-car-ca-bundle.pem
ENV SSL_CERT_FILE=/etc/ssl/certs/service-car-ca-bundle.pem

COPY . .

RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]