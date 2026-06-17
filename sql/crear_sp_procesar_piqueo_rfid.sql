CREATE OR REPLACE PROCEDURE MS_INVENTARIOS.PROCESAR_PIQUEO_RFID (
    p_numero_conteo IN VARCHAR2
) AS
    v_piqueo_id           NUMBER;
    v_estado              VARCHAR2(50);
    v_detalle_piqueo_id   NUMBER;
    v_max_secuencia_hasta NUMBER;
    v_secuencia_inicio    NUMBER;
    v_secuencia_detalle   NUMBER;
    v_secuencia_hasta     NUMBER;
    v_fecha_codigo        VARCHAR2(8);
    v_section_name        VARCHAR2(500);
    v_secuencial_id       NUMBER;
    v_proceso_id          NUMBER;
    v_sesion_id           NUMBER;
    v_total_scans         NUMBER;
    v_total_items         NUMBER;
    v_total_sincronizados NUMBER;
    v_orden_escaneo       NUMBER := 1;
    v_cedula              VARCHAR2(80) := 'RFID';
BEGIN
    IF p_numero_conteo IS NULL OR TRIM(p_numero_conteo) IS NULL THEN
        RAISE_APPLICATION_ERROR(-20000, 'Debe enviar el numero de conteo.');
    END IF;

    DBMS_OUTPUT.PUT_LINE('Iniciando proceso RFID para conteo: ' || p_numero_conteo);

    BEGIN
        SELECT piqueo_id, estado
        INTO v_piqueo_id, v_estado
        FROM MS_INVENTARIOS.INV_PIQUEOS_INVENTARIO_TBL
        WHERE numero_conteo = p_numero_conteo;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'No existe el conteo: ' || p_numero_conteo
            );
        WHEN TOO_MANY_ROWS THEN
            RAISE_APPLICATION_ERROR(
                -20002,
                'Existe mas de un conteo con numero_conteo: ' || p_numero_conteo
            );
    END;

    IF UPPER(TRIM(v_estado)) <> 'EN_PROCESO' THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'El conteo ' || p_numero_conteo ||
            ' no esta en estado EN_PROCESO. Estado actual: ' || v_estado
        );
    END IF;

    SELECT MIN(dp.detalle_piqueo_id)
    INTO v_detalle_piqueo_id
    FROM MS_INVENTARIOS.INV_DETALLE_PIQUEOS_INVENTARIOS_TBL dp
    WHERE dp.piqueo_id = v_piqueo_id;

    IF v_detalle_piqueo_id IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'No se encontro DETALLE_PIQUEO_ID para el conteo: ' || p_numero_conteo
        );
    END IF;

    SELECT COUNT(*), NVL(SUM(TRUNC(NVL(cantidad, 0))), 0)
    INTO v_total_items, v_total_scans
    FROM MS_INVENTARIOS.INV_PIQUEO_TOMA_FISICA_RFID
    WHERE numero_conteo = p_numero_conteo
      AND ean IS NOT NULL
      AND NVL(cantidad, 0) > 0
      AND NVL(UPPER(TRIM(estado)), 'PENDIENTE') <> 'SINCRONIZADO';

    IF v_total_items = 0 OR v_total_scans = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20005,
            'No existen registros RFID con EAN y cantidad positiva para el conteo: ' ||
            p_numero_conteo
        );
    END IF;

    SELECT NVL(MAX(NVL(secuencia_hasta, 0)), 0)
    INTO v_max_secuencia_hasta
    FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL
    WHERE ubicacion = 'ST'
      AND detalle_piqueo_id = v_detalle_piqueo_id;

    v_secuencia_inicio := CASE
        WHEN v_max_secuencia_hasta = 0 THEN 1
        ELSE v_max_secuencia_hasta + 1
    END;
    v_secuencia_hasta := v_secuencia_inicio;
    v_secuencia_detalle := v_secuencia_inicio;
    v_fecha_codigo := TO_CHAR(SYSDATE, 'YYYYMMDD');

    INSERT INTO MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL (
        detalle_piqueo_id,
        ubicacion,
        estado,
        secuencia_inicio,
        secuencia_hasta
    ) VALUES (
        v_detalle_piqueo_id,
        'ST',
        'ABIERTO',
        v_secuencia_inicio,
        v_secuencia_hasta
    )
    RETURNING secuencial_id INTO v_secuencial_id;

    v_section_name :=
        v_fecha_codigo ||
        v_secuencial_id ||
        v_detalle_piqueo_id ||
        'ST' ||
        v_secuencia_detalle;

    INSERT INTO MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_DETA_TBL (
        secuencial_id,
        detalle_piqueo_id,
        ubicacion,
        secuencia,
        codigo
    ) VALUES (
        v_secuencial_id,
        v_detalle_piqueo_id,
        'ST',
        v_secuencia_detalle,
        v_section_name
    );

    INSERT INTO MS_INVENTARIOS.PROCESOS_ESCANEO_TBL (
        timestamp_proceso,
        device_id,
        platform,
        total_sessions,
        total_scans,
        start_time,
        end_time,
        estado
    ) VALUES (
        SYSDATE,
        '000000001',
        'RFID',
        1,
        v_total_scans,
        SYSDATE,
        SYSDATE,
        'RECIBIDO'
    )
    RETURNING proceso_id INTO v_proceso_id;

    INSERT INTO MS_INVENTARIOS.SESIONES_ESCANEO_TBL (
        proceso_id,
        section_name,
        start_time,
        end_time,
        scan_count,
        cedula
    ) VALUES (
        v_proceso_id,
        v_section_name,
        SYSDATE,
        SYSDATE,
        v_total_scans,
        v_cedula
    )
    RETURNING sesion_id INTO v_sesion_id;

    FOR item IN (
        WITH rfid_base AS (
            SELECT
                id,
                ean,
                TRIM(descripcion) AS descripcion,
                TRUNC(NVL(cantidad, 0)) AS cantidad
            FROM MS_INVENTARIOS.INV_PIQUEO_TOMA_FISICA_RFID
            WHERE numero_conteo = p_numero_conteo
              AND ean IS NOT NULL
              AND NVL(cantidad, 0) > 0
              AND NVL(UPPER(TRIM(estado)), 'PENDIENTE') <> 'SINCRONIZADO'
        ),
        rfid_cantidad AS (
            SELECT ean, SUM(cantidad) AS cantidad
            FROM rfid_base
            GROUP BY ean
        ),
        rfid_descripcion AS (
            SELECT ean, descripcion
            FROM (
                SELECT
                    ean,
                    descripcion,
                    ROW_NUMBER() OVER (
                        PARTITION BY ean
                        ORDER BY LENGTH(descripcion) DESC NULLS LAST, id DESC
                    ) AS rn
                FROM rfid_base
            )
            WHERE rn = 1
        )
        SELECT
            c.ean,
            d.descripcion,
            c.cantidad
        FROM rfid_cantidad c
        LEFT JOIN rfid_descripcion d ON d.ean = c.ean
        ORDER BY c.ean
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Insertando EAN=' || item.ean ||
            ' DESCRIPCION=' || NVL(item.descripcion, '<NULL>') ||
            ' CANTIDAD=' || item.cantidad
        );

        FOR i IN 1 .. TRUNC(item.cantidad) LOOP
            INSERT INTO MS_INVENTARIOS.BARCODES_ESCANEO_TBL (
                sesion_id,
                proceso_id,
                codigo_barras,
                descripcion,
                orden_escaneo,
                fecha_creacion
            ) VALUES (
                v_sesion_id,
                v_proceso_id,
                item.ean,
                item.descripcion,
                v_orden_escaneo,
                SYSDATE
            );

            v_orden_escaneo := v_orden_escaneo + 1;
        END LOOP;
    END LOOP;

    UPDATE MS_INVENTARIOS.INV_PIQUEO_TOMA_FISICA_RFID
    SET estado = 'SINCRONIZADO'
    WHERE numero_conteo = p_numero_conteo
      AND ean IS NOT NULL
      AND NVL(cantidad, 0) > 0
      AND NVL(UPPER(TRIM(estado)), 'PENDIENTE') <> 'SINCRONIZADO';
    v_total_sincronizados := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE('Proceso RFID finalizado correctamente.');
    DBMS_OUTPUT.PUT_LINE('PIQUEO_ID: ' || v_piqueo_id);
    DBMS_OUTPUT.PUT_LINE('DETALLE_PIQUEO_ID: ' || v_detalle_piqueo_id);
    DBMS_OUTPUT.PUT_LINE('SECUENCIAL_ID: ' || v_secuencial_id);
    DBMS_OUTPUT.PUT_LINE('PROCESO_ID: ' || v_proceso_id);
    DBMS_OUTPUT.PUT_LINE('SESION_ID: ' || v_sesion_id);
    DBMS_OUTPUT.PUT_LINE('SECTION_NAME: ' || v_section_name);
    DBMS_OUTPUT.PUT_LINE('TOTAL_SCANS: ' || v_total_scans);
    DBMS_OUTPUT.PUT_LINE('RFID sincronizados: ' || v_total_sincronizados);
    DBMS_OUTPUT.PUT_LINE('CEDULA: ' || v_cedula);

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END PROCESAR_PIQUEO_RFID;
/

SHOW ERRORS PROCEDURE MS_INVENTARIOS.PROCESAR_PIQUEO_RFID;

-- Ejemplo:
-- SET SERVEROUTPUT ON;
-- BEGIN
--     MS_INVENTARIOS.PROCESAR_PIQUEO_RFID('NUMERO_CONTEO_AQUI');
-- END;
-- /
