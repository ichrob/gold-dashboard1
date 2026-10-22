package ch.bob.degirocompanion

/**
 * Fixed, nonfinancial navigation inside Bob's OWN website.
 * No external URLs, form submissions, credentials or broker control.
 * Browser and Bob still enforce their own login.
 */
internal object BobNavigation {
    const val origin = "https://bob-private-scanner.onrender.com/"
    private val fragments = mapOf(
        PhoneTask.OPEN_BOB to "overview",
        PhoneTask.OPEN_MARKET to "overview",
        PhoneTask.OPEN_PRODUCTS to "products",
        PhoneTask.OPEN_TRADE to "trade",
        PhoneTask.OPEN_SIMULATION to "simulation",
        PhoneTask.OPEN_LEARNING to "learning",
        PhoneTask.OPEN_RESEARCH to "research"
    )

    fun pageFor(task: PhoneTask): String? = fragments[task]

    fun urlFor(task: PhoneTask): String? = fragments[task]?.let { origin + "#" + it }

    fun urlForSection(section: String): String? =
        if (section in fragments.values) origin + "#" + section else null
}
