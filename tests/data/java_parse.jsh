// Regenerate tests/data/java_parse.txt from the repository root: jshell tests/data/java_parse.jsh
// Each line: the input (JSON string), then Double.parseDouble's result as raw IEEE-754 bits (hex), or NFE.
String[] inputs = {
  "0", "-0", "+0", "1", "-1", "+5", "7", " 7", "7 ", "\t7\n", "\u00a07", "\u20037", ".5", "5.", ".", "-.5", "+.5e1",
  "1e10", "1E10", "1e+10", "1e-10", "1e", "e5", "1e400", "-1e400", "1e-400", "4.9e-324", "2.5e-324",
  "1d", "1D", "2.5f", "2.5F", "1e5d", "1.d", ".5f", "NaN", "-NaN", "+NaN", "nan", "Infinity", "-Infinity",
  "+Infinity", "infinity", "Inf", "NaNd", "Infinityf", "0x1p3", "0X1P3", "0x1.8p1", "0x.8p1", "0x1p", "0x10",
  "0x1p3d", "-0x1p-1074", "0x1.fffffffffffffp1023", "1_000", "1,5", "1.5.5", "--1", "+-1", "", " ", "abc",
  "12345678901234567890123", "0.1", "123456789.123", "9007199254740993", "1e308", "1.7976931348623159e308",
  "\u0661", "１", "0b101", "017", "1e05", "00.5",
  "0x1p1024", "-0x1p1024", "0x1p2000", "0x1.fffffffffffff8p1023", "0x1.fffffffffffff7p1023", "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffp0", "0x1p-1080", "-0x1p-2000"
};
var sb = new StringBuilder();
for (String s : inputs) {
  String json = "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\t", "\\t").replace("\n", "\\n")
      .chars().mapToObj(c -> c < 0x20 || c > 0x7e ? String.format("\\u%04x", c) : String.valueOf((char) c))
      .reduce("", String::concat) + "\"";
  String result;
  try { result = Long.toHexString(Double.doubleToRawLongBits(Double.parseDouble(s))); }
  catch (NumberFormatException e) { result = "NFE"; }
  sb.append(json.replace("\\\\u", "\\u")).append(' ').append(result).append('\n');
}
java.nio.file.Files.writeString(java.nio.file.Path.of("tests/data/java_parse.txt"), sb.toString());
/exit
