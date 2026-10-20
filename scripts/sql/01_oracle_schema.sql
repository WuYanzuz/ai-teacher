-- ============================================================
-- 01_oracle_schema.sql — 为「作业批改/成长记录」新建独立 Oracle 用户(schema)
--
-- 适用: Oracle 19c / 21c / 23ai (多租户请连到 PDB, 如 XEPDB1, 不要连 CDB$ROOT)
-- 执行: 用 DBA 账号 (system / sysdba) 在目标 PDB 上执行
--   sqlplus system/<密码>@//主机:端口/服务名 @01_oracle_schema.sql
--
-- 执行前: 把下面的 <CHANGE_ME> 换成真实强密码
-- 如表空间已由 DBA 建好, 注释掉第 1 步即可
-- ============================================================

-- 1. 表空间 (100MB 起, 自动扩展)
CREATE TABLESPACE aiwechat
  DATAFILE 'aiwechat01.dbf'
  SIZE 100M
  AUTOEXTEND ON
  NEXT 50M
  MAXSIZE 4G
  EXTENT MANAGEMENT LOCAL
  SEGMENT SPACE MANAGEMENT AUTO;

-- 2. 用户 (= 一个独立 schema)
CREATE USER AIWECHAT
  IDENTIFIED BY "<CHANGE_ME>"
  DEFAULT TABLESPACE aiwechat
  QUOTA UNLIMITED ON aiwechat;

-- 3. 权限
--    CREATE SESSION  连接
--    CREATE TABLE    建表 (IDENTITY 列会自动创建序列)
--    CREATE SEQUENCE / TRIGGER / VIEW  备用
GRANT CREATE SESSION,
      CREATE TABLE,
      CREATE SEQUENCE,
      CREATE TRIGGER,
      CREATE VIEW
  TO AIWECHAT;

-- 验证:
--   SELECT username, default_tablespace FROM dba_users WHERE username = 'AIWECHAT';
-- 之后用 AIWECHAT 账号跑 scripts/check_oracle.py 验证连通, 首次启动后端会自动建表。
