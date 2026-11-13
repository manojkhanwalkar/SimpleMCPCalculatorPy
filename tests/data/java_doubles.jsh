// Regenerate tests/data/java_doubles.txt from the repository root: jshell tests/data/java_doubles.jsh
// Each line: raw IEEE-754 bits (hex), Double.toString(d), Double.toString(Math.rint(d)).
var r = new java.util.Random(20261113L);
var sb = new StringBuilder();
for (int i = 0; i < 5000; i++) {
  double d;
  switch (i % 4) {
    case 0 -> d = Double.longBitsToDouble(r.nextLong());
    case 1 -> d = r.nextDouble() * Math.pow(10, r.nextInt(40) - 20);
    case 2 -> d = (double) r.nextInt(100000) / Math.pow(10, r.nextInt(12));
    default -> d = (r.nextBoolean() ? -1 : 1) * Math.scalb(1.0, r.nextInt(2098) - 1074);
  }
  sb.append(Long.toHexString(Double.doubleToRawLongBits(d))).append(' ').append(Double.toString(d)).append(' ').append(Double.toString(Math.rint(d))).append('\n');
}
java.nio.file.Files.writeString(java.nio.file.Path.of("tests/data/java_doubles.txt"), sb.toString());
/exit
