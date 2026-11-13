// Regenerate tests/data/java_ipow.txt from the repository root: jshell tests/data/java_ipow.jsh
// Each line: base, exponent, Math.pow(base, exponent) as raw IEEE-754 bits (hex).
var sb = new StringBuilder();
long[] bigs = {1000, 12345, 99999, 1000000007L, 123456789L, 9007199254740991L, 1L<<40, 3L*1000000000L, 999999999999L};
java.util.List<Long> bases = new java.util.ArrayList<>();
for (long b = -50; b <= 50; b++) bases.add(b);
for (long b : bigs) { bases.add(b); bases.add(-b); }
for (long a : bases) for (int e = -64; e <= 64; e++)
  sb.append(a).append(' ').append(e).append(' ').append(Long.toHexString(Double.doubleToRawLongBits(Math.pow((double) a, (double) e)))).append('\n');
java.nio.file.Files.writeString(java.nio.file.Path.of("tests/data/java_ipow.txt"), sb.toString());
/exit
