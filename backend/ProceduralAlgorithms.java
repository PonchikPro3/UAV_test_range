import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Properties;
import java.util.Set;

/** Procedural prototype: all operations are static; no domain class hierarchy. */
public final class ProceduralAlgorithms {
    static Instant timestamp(String text) {
        return OffsetDateTime.parse(text).toInstant();
    }

    static String required(Properties p, String key) {
        String value = p.getProperty(key, "").trim();
        if (value.isEmpty()) throw new IllegalArgumentException("Missing " + key);
        return value;
    }

    static boolean flag(String text) {
        if (!text.equals("true") && !text.equals("false")) {
            throw new IllegalArgumentException("Expected true or false: " + text);
        }
        return Boolean.parseBoolean(text);
    }

    static String identifier(String text) {
        if (!text.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid identifier: " + text);
        }
        return text;
    }

    static Set<String> identifiers(String text) {
        Set<String> result = new HashSet<>();
        if (!text.trim().isEmpty()) {
            for (String token : text.split(",", -1)) result.add(identifier(token.trim()));
        }
        return result;
    }

    static void validateTarget(Properties p) {
        identifier(required(p, "test_id"));
        identifier(required(p, "zone_id"));
        identifier(required(p, "uav_id"));
        Instant start = timestamp(required(p, "start"));
        Instant end = timestamp(required(p, "end"));
        if (!start.isBefore(end)) throw new IllegalArgumentException("start must precede end");
        flag(required(p, "interference"));
    }

    /** A1. Returns all missing, unapproved or expired document type identifiers. */
    static List<String> checkReadiness(Properties p) {
        validateTarget(p);
        Instant end = timestamp(required(p, "end"));
        List<String> failures = new ArrayList<>();
        for (String type : required(p, "required_docs").split(",", -1)) {
            type = identifier(type.trim());
            String approval = p.getProperty("document." + type + ".approved", "false");
            String expiry = p.getProperty("document." + type + ".expires", "");
            if (!flag(approval) || expiry.isEmpty() || timestamp(expiry).isBefore(end)) {
                failures.add(type);
            }
        }
        return failures;
    }

    /** A2. Half-open intervals: [start,end); O(n+a) expected, including lookup setup. */
    static List<String> findConflicts(Properties p, List<String[]> bookings) {
        validateTarget(p);
        Instant start = timestamp(required(p, "start"));
        Instant end = timestamp(required(p, "end"));
        String zone = required(p, "zone_id");
        String uav = required(p, "uav_id");
        String test = required(p, "test_id");
        boolean interference = flag(required(p, "interference"));
        Set<String> adjacent = identifiers(p.getProperty("adjacent_zones", ""));
        List<String> conflicts = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (String[] b : bookings) {
            if (b.length != 7) throw new IllegalArgumentException("Booking must have 7 fields");
            String id = identifier(b[0]);
            identifier(b[1]); identifier(b[2]);
            if (!seen.add(id)) throw new IllegalArgumentException("Duplicate test_id: " + id);
            Instant bs = timestamp(b[3]);
            Instant be = timestamp(b[4]);
            if (!bs.isBefore(be)) throw new IllegalArgumentException("Invalid booking interval");
            if (!Set.of("PLANNED", "APPROVED", "RUNNING", "CANCELLED", "COMPLETED").contains(b[5])) {
                throw new IllegalArgumentException("Unknown booking status");
            }
            boolean otherInterference = flag(b[6]);
            if (id.equals(test) || b[5].equals("CANCELLED") || b[5].equals("COMPLETED")) continue;
            boolean overlap = start.isBefore(be) && bs.isBefore(end);
            if (!overlap) continue;
            List<String> reasons = new ArrayList<>();
            if (zone.equals(b[1])) reasons.add("SAME_ZONE");
            if (uav.equals(b[2])) reasons.add("SAME_UAV");
            if (adjacent.contains(b[1]) && (interference || otherInterference)) {
                reasons.add("ADJACENT_INTERFERENCE");
            }
            if (!reasons.isEmpty()) conflicts.add(id + ":" + String.join("+", reasons));
        }
        return conflicts;
    }

    static List<String[]> readBookings(Path path) throws IOException {
        List<String[]> result = new ArrayList<>();
        try (java.io.BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            String header = reader.readLine();
            if (!"test_id,zone_id,uav_id,start,end,status,interference".equals(header)) {
                throw new IllegalArgumentException("Invalid schedule header");
            }
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) continue;
                String[] fields = line.split(",", -1);
                for (int i = 0; i < fields.length; i++) fields[i] = fields[i].trim();
                result.add(fields);
            }
        }
        return result;
    }

    static String jsonArray(List<String> values) {
        // Values contain validated identifiers and fixed reason codes only.
        return "[" + values.stream().map(x -> "\"" + x + "\"")
                .collect(java.util.stream.Collectors.joining(",")) + "]";
    }

    public static void main(String[] args) {
        try {
            if (args.length != 2) throw new IllegalArgumentException("Use: target.properties schedule.csv");
            Properties p = new Properties();
            try (Reader r = Files.newBufferedReader(Path.of(args[0]), StandardCharsets.UTF_8)) { p.load(r); }
            List<String> failures = checkReadiness(p);
            List<String> conflicts = findConflicts(p, readBookings(Path.of(args[1])));
            System.out.println("{\"test_id\":\"" + required(p, "test_id")
                    + "\",\"ready\":" + failures.isEmpty()
                    + ",\"can_book\":" + (failures.isEmpty() && conflicts.isEmpty())
                    + ",\"document_failures\":" + jsonArray(failures)
                    + ",\"conflicts\":" + jsonArray(conflicts) + "}");
        } catch (Exception e) {
            System.err.println("Input error: " + e.getMessage());
            System.exit(2);
        }
    }
}
