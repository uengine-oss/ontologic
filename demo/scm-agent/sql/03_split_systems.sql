-- 공급망 데이터를 **이기종 업무 시스템**으로 분리한다 (PostgreSQL 쪽).
--
-- 왜 나누는가 — 데이터 패브릭이 하는 일은 "한 스키마 안의 테이블을 읽는 것"이 아니라
-- **서로 다른 시스템에 흩어진 것을 하나의 지식지도로 잇는 것**이다. 한 스키마에 다 넣으면
-- 연계 계층은 아무 일도 하지 않는 셈이 되고, 데모가 증명하는 것도 없어진다.
--
--   erp     (PostgreSQL) — 구매·조달 기간계 : 공급사·품목·계약·발주·발주라인
--   customs (PostgreSQL) — 관세/통관 시스템 : 수출입 신고
--   wms     (MySQL)      — 창고·운송      : 선적·일별 재고      (04_wms_crm_mysql.sql)
--   crm     (MySQL)      — 고객관리        : 고객·주문·클레임    (04_wms_crm_mysql.sql)
--
-- 시스템마다 **키 표기가 다르다**. 실제 기업이 그렇기 때문이고, 그 차이를 흡수하는 것이
-- 온톨로지가 하는 일이다. ERP 는 `supplier_id`, WMS 는 `vendor_code`, CRM 은 `cust_no` 를
-- 쓴다. 같은 것을 다르게 부르는 상태를 남겨 두어야 연계가 실제 문제가 된다.

DROP SCHEMA IF EXISTS erp CASCADE;
DROP SCHEMA IF EXISTS customs CASCADE;
CREATE SCHEMA erp;
CREATE SCHEMA customs;

-- ── ERP : 구매·조달 기간계 ────────────────────────────────────────────────
CREATE TABLE erp.mst_supplier AS
SELECT supplier_id, supplier_name, country, city, tier, category,
       rating AS eval_score, avg_lead_days AS lead_time_days,
       on_time_rate AS otd_rate, incoterms, currency
FROM supplychain.scm_supplier;
ALTER TABLE erp.mst_supplier ADD PRIMARY KEY (supplier_id);

CREATE TABLE erp.mst_item AS
SELECT item_id, item_name, item_type, hs_code, origin_country, unit,
       std_cost_usd, safety_stock, moq,
       primary_supplier_id, alt_supplier_id
FROM supplychain.scm_item;
ALTER TABLE erp.mst_item ADD PRIMARY KEY (item_id);

CREATE TABLE erp.doc_contract AS
SELECT contract_id, supplier_id, contract_type, start_date, end_date,
       auto_renew, penalty_rate, price_lock, status, risk_clause
FROM supplychain.scm_contract;
ALTER TABLE erp.doc_contract ADD PRIMARY KEY (contract_id);

CREATE TABLE erp.doc_purchase_order AS
SELECT po_id, supplier_id, contract_id, order_date, promised_date,
       status, total_amount_usd, buyer, priority
FROM supplychain.scm_purchase_order;
ALTER TABLE erp.doc_purchase_order ADD PRIMARY KEY (po_id);

CREATE TABLE erp.doc_po_line AS
SELECT po_line_id, po_id, item_id, qty_ordered, qty_received,
       unit_price_usd, line_status
FROM supplychain.scm_po_line;
ALTER TABLE erp.doc_po_line ADD PRIMARY KEY (po_line_id);

ALTER TABLE erp.mst_item        ADD FOREIGN KEY (primary_supplier_id) REFERENCES erp.mst_supplier(supplier_id);
ALTER TABLE erp.doc_contract    ADD FOREIGN KEY (supplier_id)         REFERENCES erp.mst_supplier(supplier_id);
ALTER TABLE erp.doc_purchase_order ADD FOREIGN KEY (supplier_id)      REFERENCES erp.mst_supplier(supplier_id);
ALTER TABLE erp.doc_purchase_order ADD FOREIGN KEY (contract_id)      REFERENCES erp.doc_contract(contract_id);
ALTER TABLE erp.doc_po_line     ADD FOREIGN KEY (po_id)               REFERENCES erp.doc_purchase_order(po_id);
ALTER TABLE erp.doc_po_line     ADD FOREIGN KEY (item_id)             REFERENCES erp.mst_item(item_id);

-- ── 관세/통관 시스템 ──────────────────────────────────────────────────────
-- 통관 시스템은 ERP 를 모른다. 선적번호와 품목코드 문자열만 들고 있다 (FK 없음).
-- 이 단절이 온톨로지가 이어야 할 지점이다.
CREATE TABLE customs.decl_header AS
SELECT decl_id, shipment_id AS ref_shipment_no, direction, item_id AS ref_item_code,
       declared_hs_code, origin_country, fta_applied, coo_required, coo_attached,
       invoice_value_usd, duty_rate, status, hold_reason, filed_date
FROM supplychain.scm_customs_declaration;
ALTER TABLE customs.decl_header ADD PRIMARY KEY (decl_id);

CREATE INDEX ON customs.decl_header (ref_shipment_no);
CREATE INDEX ON customs.decl_header (ref_item_code);
