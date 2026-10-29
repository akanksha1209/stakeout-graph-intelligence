import pyTigerGraph as tg
from app.config import TG_HOST, TG_USERNAME, TG_PASSWORD

print("Connecting to TigerGraph...")
conn = tg.TigerGraphConnection(host=TG_HOST, username=TG_USERNAME, password=TG_PASSWORD)

schema = """
USE GLOBAL
DROP ALL
CREATE VERTEX Wallet (PRIMARY_ID address STRING, is_exit_point BOOL DEFAULT "false", data_source STRING DEFAULT "synthetic") WITH primary_id_as_attribute="true"
CREATE VERTEX Report (PRIMARY_ID report_id STRING, target_address STRING, evidence_hash STRING, reporter STRING, timestamp INT, data_source STRING DEFAULT "synthetic") WITH primary_id_as_attribute="true"
CREATE VERTEX Cluster (PRIMARY_ID cluster_id STRING, data_source STRING DEFAULT "synthetic") WITH primary_id_as_attribute="true"
CREATE DIRECTED EDGE TRANSFER (FROM Wallet, TO Wallet, amount DOUBLE, timestamp INT, tx_id STRING, data_source STRING) WITH REVERSE_EDGE="REVERSE_TRANSFER"
CREATE DIRECTED EDGE REPORTED (FROM Report, TO Wallet, data_source STRING) WITH REVERSE_EDGE="WALLET_HAS_REPORT"
CREATE DIRECTED EDGE MEMBER_OF (FROM Wallet, TO Cluster, data_source STRING) WITH REVERSE_EDGE="CLUSTER_HAS_MEMBER"
CREATE GRAPH StakeoutFinal (*)
"""

q1 = """
USE GRAPH StakeoutFinal
CREATE OR REPLACE QUERY analyze_wallet(STRING target_address) FOR GRAPH StakeoutFinal {
  SumAccum<DOUBLE> @@total_in, @@total_out;
  SumAccum<INT> @@in_degree, @@out_degree, @@outflows_to_cluster;
  SetAccum<STRING> @@cluster_ids, @@members, @@exit_points, @@reporters;
  OrAccum @is_target_cluster;
  Start = {Wallet.*};
  TargetNode = SELECT w FROM Start:w WHERE w.address == target_address;
  Outs = SELECT t FROM TargetNode:t -(TRANSFER:e)-> Wallet:v ACCUM @@total_out += e.amount, @@out_degree += 1;
  Ins = SELECT s FROM Start:s -(TRANSFER:e)-> Wallet:t WHERE t.address == target_address ACCUM @@total_in += e.amount, @@in_degree += 1;
  Clus = SELECT c FROM TargetNode:w -(MEMBER_OF:e)-> Cluster:c POST-ACCUM c.@is_target_cluster = TRUE, @@cluster_ids += c.cluster_id;
  Mem = SELECT m FROM Start:m -(MEMBER_OF:e)-> Cluster:c WHERE c.@is_target_cluster == TRUE ACCUM @@members += m.address, IF m.is_exit_point THEN @@exit_points += m.address END;
  
  // Removed the Reps traversal to avoid V1 compiler bug. Reporters will be empty.
  PRINT TargetNode.size() AS found, @@total_in AS total_in, @@total_out AS total_out, @@in_degree AS in_degree, @@out_degree AS out_degree, @@cluster_ids AS clusterIds, @@members AS membersList, @@exit_points AS exitPointsList, @@reporters AS reporters, @@outflows_to_cluster AS outflowsToCluster;
}
INSTALL QUERY analyze_wallet
"""

q2 = """
USE GRAPH StakeoutFinal
CREATE OR REPLACE QUERY get_cluster_graph(STRING target_cluster) FOR GRAPH StakeoutFinal {
  SetAccum<EDGE> @@edges;
  Start   = {Cluster.*};
  C       = SELECT c FROM Start:c WHERE c.cluster_id == target_cluster;
  Members = SELECT w FROM C:c -(CLUSTER_HAS_MEMBER:e)-> Wallet:w;
  Outflow = SELECT t FROM Members:s -(TRANSFER:e)-> Wallet:t ACCUM @@edges += e;
  PRINT Members[Members.address AS address, Members.is_exit_point AS is_exit_point, Members.data_source AS data_source];
  PRINT @@edges AS transfers;
}
INSTALL QUERY get_cluster_graph
"""

print("Building Schema...")
print(conn.gsql(schema))
print("Installing Queries...")
print(conn.gsql(q1))
print(conn.gsql(q2))
print("Setup Complete.")
