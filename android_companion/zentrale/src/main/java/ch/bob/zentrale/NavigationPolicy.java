package ch.bob.zentrale;
import java.net.URI;
final class NavigationPolicy {
    static final String HOME = "https://bob-private-scanner.onrender.com/zentrale/";
    static boolean internal(String value) {
        try {
            URI uri = new URI(value);
            return "https".equalsIgnoreCase(uri.getScheme())
                && "bob-private-scanner.onrender.com".equalsIgnoreCase(uri.getHost())
                && uri.getRawUserInfo() == null && (uri.getPort() == -1 || uri.getPort() == 443);
        } catch (Exception ignored) { return false; }
    }
}
