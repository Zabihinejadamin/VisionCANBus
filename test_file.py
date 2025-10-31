import cantools

# Load DBC
db = cantools.database.load_file('DBC/vcu_official.dbc')

# Your real data
data_hex = "54400054F8112800"
data = bytes.fromhex(data_hex)

# Decode
try:
    decoded = db.decode_message(1831, data)
    print("DECODED 0x727:")
    print(f"  Throttle: {decoded['VCU_PCU_THROTTLE']}%")
    print(f"  Drive:    {'DRIVE' if decoded['VCU_PCU_DRIVE'] else 'NOT DRIVE'}")
    print(f"  UV Limit: {decoded['VCU_PCU_UV_LIMIT']:.1f} V")
    print(f"  Max Cur:  {decoded['VCU_PCU_MAXCUR_LIMIT']} A")
except Exception as e:
    print("ERROR:", e)