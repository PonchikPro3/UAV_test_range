import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

/** Regression checks for the scheduling and readiness rules. */
public final class AlgorithmChecks {
    static int checks = 0;
    static void check(boolean condition, String name) {
        checks++;
        if (!condition) throw new AssertionError(name);
    }
    static void rejects(Runnable operation, String name) {
        boolean rejected = false;
        try { operation.run(); } catch (IllegalArgumentException e) { rejected = true; }
        check(rejected, name);
    }
    static Properties target() {
        Properties p = new Properties();
        p.setProperty("test_id", "R-001"); p.setProperty("zone_id", "A");
        p.setProperty("uav_id", "UAV-01");
        p.setProperty("start", "2026-11-02T10:00:00+03:00");
        p.setProperty("end", "2026-11-02T11:00:00+03:00");
        p.setProperty("interference", "false"); p.setProperty("adjacent_zones", "B");
        p.setProperty("required_docs", "CHECKLIST");
        p.setProperty("document.CHECKLIST.approved", "true");
        p.setProperty("document.CHECKLIST.expires", "2026-11-02T11:00:00+03:00");
        return p;
    }
    static List<String[]> booking(String id, String zone, String uav, String start, String end,
                                  String status, String interference) {
        List<String[]> rows = new ArrayList<>();
        rows.add(new String[]{id, zone, uav, start, end, status, interference});
        return rows;
    }
    static List<String[]> booking(String zone, String uav, String status, String interference) {
        return booking("T1", zone, uav, "2026-11-02T10:30:00+03:00",
                "2026-11-02T11:30:00+03:00", status, interference);
    }
    public static void main(String[] args) throws Exception {
        Properties p = target();
        check(ProceduralAlgorithms.checkReadiness(p).isEmpty(), "expiry equal to end");
        p.setProperty("document.CHECKLIST.expires", "2026-11-02T10:59:59+03:00");
        check(ProceduralAlgorithms.checkReadiness(p).size() == 1, "expired document");
        p = target(); p.remove("document.CHECKLIST.expires");
        check(ProceduralAlgorithms.checkReadiness(p).size() == 1, "missing document");
        p = target(); p.setProperty("document.CHECKLIST.approved", "false");
        check(ProceduralAlgorithms.checkReadiness(p).size() == 1, "unapproved document");
        Properties base = target();
        check(ProceduralAlgorithms.findConflicts(base, booking("A", "OTHER", "APPROVED", "false")).size() == 1, "same zone");
        check(ProceduralAlgorithms.findConflicts(base, booking("C", "UAV-01", "PLANNED", "false")).size() == 1, "same UAV");
        check(ProceduralAlgorithms.findConflicts(base, booking("B", "OTHER", "RUNNING", "true")).size() == 1, "adjacent interference");
        check(ProceduralAlgorithms.findConflicts(base, booking("B", "OTHER", "APPROVED", "false")).isEmpty(), "adjacent compatible");
        check(ProceduralAlgorithms.findConflicts(base, booking("C", "OTHER", "APPROVED", "true")).isEmpty(), "non-adjacent");
        for (String state : List.of("CANCELLED", "COMPLETED")) {
            check(ProceduralAlgorithms.findConflicts(base, booking("A", "UAV-01", state, "true")).isEmpty(), state);
        }
        check(ProceduralAlgorithms.findConflicts(base, booking("T1", "A", "OTHER", "2026-11-02T09:00:00+03:00", "2026-11-02T10:00:00+03:00", "APPROVED", "false")).isEmpty(), "touch before");
        check(ProceduralAlgorithms.findConflicts(base, booking("T1", "A", "OTHER", "2026-11-02T11:00:00+03:00", "2026-11-02T12:00:00+03:00", "APPROVED", "false")).isEmpty(), "touch after");
        check(ProceduralAlgorithms.findConflicts(base, booking("R-001", "A", "UAV-01", "2026-11-02T10:00:00+03:00", "2026-11-02T11:00:00+03:00", "APPROVED", "false")).isEmpty(), "exclude self");
        check(ProceduralAlgorithms.findConflicts(base, booking("T1", "A", "OTHER", "2026-11-02T07:30:00Z", "2026-11-02T08:30:00Z", "APPROVED", "false")).size() == 1, "time zone normalization");
        check(ProceduralAlgorithms.findConflicts(base, List.of()).isEmpty(), "empty schedule");
        Properties active = target(); active.setProperty("interference", "true");
        check(ProceduralAlgorithms.findConflicts(active, booking("B", "OTHER", "APPROVED", "false")).size() == 1, "target interference");
        Properties invalid = target(); invalid.setProperty("end", invalid.getProperty("start"));
        rejects(() -> ProceduralAlgorithms.checkReadiness(invalid), "zero interval");
        Properties badFlag = target(); badFlag.setProperty("interference", "yes");
        rejects(() -> ProceduralAlgorithms.checkReadiness(badFlag), "invalid boolean");
        Properties badId = target(); badId.setProperty("test_id", "x\"y");
        rejects(() -> ProceduralAlgorithms.checkReadiness(badId), "invalid identifier");
        rejects(() -> ProceduralAlgorithms.findConflicts(base, booking("A", "OTHER", "UNKNOWN", "false")), "unknown state");
        List<String[]> duplicates = booking("A", "OTHER", "APPROVED", "false");
        duplicates.add(duplicates.get(0));
        rejects(() -> ProceduralAlgorithms.findConflicts(base, duplicates), "duplicate booking");
        Path badCsv = Files.createTempFile("schedule-check", ".csv");
        try {
            Files.writeString(badCsv, "wrong,header\n", StandardCharsets.UTF_8);
            boolean rejected = false;
            try { ProceduralAlgorithms.readBookings(badCsv); } catch (IllegalArgumentException e) { rejected = true; }
            check(rejected, "invalid schedule header");
        } finally { Files.deleteIfExists(badCsv); }
        System.out.println("JAVA_CHECKS_PASSED=" + checks);
    }
}
