export interface Persona {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
}
export interface Result {
  success: boolean;
  summary: string;
  score?: number | null;
  score_justification?: string | null;
  failure_reason?: string | null;
  steps: {
    step: number;
    action: string;
    reasoning: string;
    outcome: string;
    value?: string | null;
    screenshot_url?: string | null;
  }[];
  access_checks?: { state: string; evidence: string[] }[];
}
export interface Run {
  id: string;
  url: string;
  task: string;
  personas: string[];
  persona_definitions?: Record<string, Persona>;
  status: "created" | "running" | "completed" | "failed";
  session_viewer_urls: Record<string, string>;
  results: Record<string, Result>;
  errors: Record<string, string>;
  createdAt?: string;
}
export const fallbackPersonas: Persona[] = [
  {
    id: "first_time",
    name: "First-Time User",
    description:
      "New to the site and reliant on visible labels and familiar navigation.",
    system_prompt: "",
  },
  {
    id: "power_user",
    name: "Power User",
    description:
      "Experienced with web apps and focused on the shortest path to a result.",
    system_prompt: "",
  },
  {
    id: "elderly",
    name: "Older adult",
    description:
      "Needs readable text, clear controls, and time to confirm each action.",
    system_prompt: "",
  },
  {
    id: "mobile_user",
    name: "Mobile User",
    description:
      "On a small screen, moving quickly with one hand and limited time.",
    system_prompt: "",
  },
  {
    id: "accessibility_advocate",
    name: "Accessibility Advocate",
    description:
      "Checks keyboard flow, focus states, structure, and clear feedback.",
    system_prompt: "",
  },
  {
    id: "privacy_conscious",
    name: "Privacy-Conscious User",
    description:
      "Wants to understand data use before sharing information or continuing.",
    system_prompt: "",
  },
];


type DemoSpec = {
  id: string;
  url: string;
  task: string;
  personas: string[];
  scores: number[];
  summary: string;
  issuePersona?: string;
  issuePersonas?: string[];
  issueReason?: string;
};

const demoPersonaLabels: Record<string, string> = {
  first_time: "First-time user",
  power_user: "Power user",
  elderly: "Older adult",
  mobile_user: "Mobile user",
  accessibility_advocate: "Accessibility advocate",
  privacy_conscious: "Privacy-conscious user",
};

function demoSteps(task: string, personaId: string, blocked = false) {
  const actions = ["navigate", "search", "click", "verify"];
  const count = blocked ? 3 : 4;
  return Array.from({ length: count }, (_, index) => ({
    step: index + 1,
    action: actions[index],
    reasoning:
      index === 0
        ? `${demoPersonaLabels[personaId]} looks for a clear starting point for “${task}”.`
        : index === 1
          ? "The visible labels and page structure suggest the next path."
          : index === 2
            ? "The control appears to match the goal, so I will continue and check the response."
            : "The result confirms whether the requested task is complete.",
    outcome:
      blocked && index === count - 1
        ? "The expected control was not reachable from this state."
        : "ok",
  }));
}

function buildDemoRun(spec: DemoSpec): Run {
  const results: Record<string, Result> = {};
  spec.personas.forEach((personaId, index) => {
    const score = spec.scores[index] ?? 8.5;
    const blocked =
      spec.issuePersona === personaId || spec.issuePersonas?.includes(personaId);
    results[personaId] = blocked
      ? {
          success: false,
          score,
          summary: spec.issueReason || "The agent made progress but could not finish the requested task.",
          failure_reason: "no_progress",
          score_justification:
            "The primary path was understandable, but one interaction blocked completion for this persona.",
          steps: demoSteps(spec.task, personaId, true),
        }
      : {
          success: true,
          score,
          summary: `${spec.summary} ${demoPersonaLabels[personaId]} completed the path with the available controls.`,
          score_justification:
            score >= 9
              ? "The path was easy to discover and the interface gave clear confirmation after each key action."
              : "The task was completed, but the persona needed an extra scan to find the next action.",
          steps: demoSteps(spec.task, personaId),
        };
  });
  return {
    id: spec.id,
    url: spec.url,
    task: spec.task,
    personas: spec.personas,
    status: "completed",
    session_viewer_urls: {},
    errors: {},
    results,
  };
}

function blockedDemoResult(
  score: number,
  task: string,
  personaId: string,
  reason: string,
): Result {
  return {
    success: false,
    score,
    summary: reason,
    failure_reason: "no_progress",
    score_justification:
      "The primary path was understandable, but one interaction blocked completion for this persona.",
    steps: demoSteps(task, personaId, true),
  };
}

const additionalDemoSpecs: DemoSpec[] = [
  {
    id: "demo-4",
    url: "https://www.figma.com",
    task: "Find a design file in the Community library",
    personas: ["first_time", "power_user", "accessibility_advocate"],
    scores: [8.9, 9.7, 8.6],
    summary: "Located a Community resource and opened the file preview.",
    issuePersona: "accessibility_advocate",
    issueReason: "The file preview opened, but the keyboard focus moved behind the dialog and the agent could not reach its close control.",
  },
  {
    id: "demo-5",
    url: "https://slack.com",
    task: "Find the project updates channel",
    personas: ["first_time", "mobile_user", "privacy_conscious", "power_user"],
    scores: [8.7, 7.9, 8.8, 9.6],
    summary: "Found the relevant workspace conversation and confirmed the channel context.",
    issuePersona: "mobile_user",
    issueReason: "The compact navigation collapsed before the mobile agent could confirm the channel.",
  },
  {
    id: "demo-6",
    url: "https://linear.app",
    task: "Create a project and assign a due date",
    personas: ["power_user", "first_time", "accessibility_advocate"],
    scores: [9.8, 8.4, 9.1],
    summary: "Created a project, assigned an owner, and set a due date.",
    issuePersona: "first_time",
    issueReason: "The create flow used an unlabeled icon for the due-date field, forcing the first-time agent to search the form.",
  },
  {
    id: "demo-7",
    url: "https://vercel.com",
    task: "Deploy a project from a Git repository",
    personas: ["power_user", "mobile_user", "privacy_conscious"],
    scores: [9.5, 8.2, 8.8],
    summary: "Reached the deployment setup and verified the repository selection.",
    issuePersona: "mobile_user",
    issueReason: "The repository picker extended beyond the mobile viewport and the final confirmation was below the fold.",
  },
  {
    id: "demo-8",
    url: "https://docs.stripe.com",
    task: "Find the checkout API reference",
    personas: ["first_time", "power_user", "accessibility_advocate", "privacy_conscious"],
    scores: [8.6, 9.9, 9.2, 8.8],
    summary: "Used documentation navigation and search to reach the Checkout API reference.",
    issuePersona: "first_time",
    issuePersonas: ["privacy_conscious"],
    issueReason: "The docs navigation had two similarly named Checkout sections, which made the first-time path loop once.",
  },
  {
    id: "demo-9",
    url: "https://www.canva.com",
    task: "Create a social post from a template",
    personas: ["first_time", "mobile_user", "elderly"],
    scores: [9.1, 8.3, 7.8],
    summary: "Selected a template and reached the editor with the canvas loaded.",
    issuePersona: "elderly",
    issueReason: "The template action labels became truncated at larger zoom, so the agent could not distinguish duplicate options.",
  },
  {
    id: "demo-10",
    url: "https://www.duolingo.com",
    task: "Start a beginner language lesson",
    personas: ["first_time", "mobile_user", "elderly", "privacy_conscious"],
    scores: [9.4, 9.0, 8.1, 8.8],
    summary: "Selected a beginner path and started the first lesson.",
    issuePersona: "privacy_conscious",
    issuePersonas: ["mobile_user"],
    issueReason: "The lesson flow presented a required account prompt before explaining which profile data would be stored.",
  },
  {
    id: "demo-11",
    url: "https://open.spotify.com",
    task: "Find a playlist and save a track",
    personas: ["power_user", "mobile_user", "first_time"],
    scores: [9.8, 9.2, 8.6],
    summary: "Found the playlist and saved a track from the results view.",
    issuePersona: "first_time",
    issueReason: "The save control used an unlabeled icon and the confirmation was easy to miss in the results list.",
  },
  {
    id: "demo-12",
    url: "https://mail.google.com",
    task: "Search for an email and open the latest thread",
    personas: ["power_user", "first_time", "accessibility_advocate", "privacy_conscious"],
    scores: [9.7, 8.8, 9.0, 8.9],
    summary: "Searched the inbox and opened the newest matching conversation.",
    issuePersona: "accessibility_advocate",
    issuePersonas: ["privacy_conscious"],
    issueReason: "The search results updated without moving focus, leaving the keyboard agent unsure which result was active.",
  },
  {
    id: "demo-13",
    url: "https://drive.google.com",
    task: "Find a shared document and open it",
    personas: ["first_time", "power_user", "mobile_user"],
    scores: [8.9, 9.6, 8.4],
    summary: "Located a shared document and opened the correct file.",
    issuePersona: "mobile_user",
    issueReason: "The shared-file list required horizontal scrolling to reveal the open action on a narrow viewport.",
  },
  {
    id: "demo-14",
    url: "https://calendar.google.com",
    task: "Create a calendar event",
    personas: ["first_time", "elderly", "accessibility_advocate", "mobile_user"],
    scores: [8.7, 7.9, 9.1, 8.8],
    summary: "Created an event with a title, time, and confirmation state.",
    issuePersona: "elderly",
    issuePersonas: ["mobile_user"],
    issueReason: "The time picker relied on small increment controls and did not clearly announce the selected time.",
  },
  {
    id: "demo-15",
    url: "https://www.amazon.com",
    task: "Find a product with next-day delivery",
    personas: ["power_user", "first_time", "elderly", "privacy_conscious"],
    scores: [9.4, 8.5, 7.4, 8.2],
    summary: "Compared product cards and reached a listing with delivery information.",
    issuePersona: "elderly",
    issueReason: "Delivery filters were difficult to distinguish after increasing the page zoom.",
  },
  {
    id: "demo-16",
    url: "https://github.com",
    task: "Open a pull request checklist",
    personas: ["power_user", "first_time", "accessibility_advocate"],
    scores: [9.9, 8.6, 9.3],
    summary: "Opened the repository workflow and found the pull request checklist.",
    issuePersona: "accessibility_advocate",
    issueReason: "The checklist accordion changed state visually but did not expose the expanded content to keyboard navigation.",
  },
  {
    id: "demo-17",
    url: "https://stackoverflow.com",
    task: "Find an answer about async JavaScript",
    personas: ["power_user", "first_time", "mobile_user"],
    scores: [9.5, 8.7, 8.5],
    summary: "Searched the question index and opened a highly relevant answer.",
    issuePersona: "mobile_user",
    issueReason: "The answer list was dense on mobile and the accepted-answer marker was below the initial viewport.",
  },
  {
    id: "demo-18",
    url: "https://www.coursera.org",
    task: "Enroll in a course and view the first lesson",
    personas: ["first_time", "privacy_conscious", "elderly", "mobile_user"],
    scores: [8.8, 8.1, 7.7, 8.5],
    summary: "Reached the course overview and opened the first lesson preview.",
    issuePersona: "privacy_conscious",
    issuePersonas: ["elderly"],
    issueReason: "Enrollment asked for profile details before showing whether the first lesson could be previewed without signing up.",
  },
  {
    id: "demo-19",
    url: "https://m.uber.com",
    task: "Request a ride to a saved location",
    personas: ["mobile_user", "first_time", "privacy_conscious"],
    scores: [9.1, 8.4, 7.9],
    summary: "Selected a saved destination and reached the ride confirmation step.",
    issuePersona: "privacy_conscious",
    issueReason: "Location permission copy appeared after the destination was selected, making the data request feel unexpected.",
  },
  {
    id: "demo-20",
    url: "https://www.nytimes.com",
    task: "Find the latest technology newsletter",
    personas: ["first_time", "power_user", "privacy_conscious", "accessibility_advocate"],
    scores: [8.5, 9.3, 8.0, 8.8],
    summary: "Used the site navigation to locate the technology newsletter page.",
    issuePersona: "first_time",
    issuePersonas: ["privacy_conscious"],
    issueReason: "The newsletter page was discoverable only through a footer link, so the first-time agent missed it in the main navigation.",
  },
];

const shoppingSteps = [
  {
    step: 1,
    action: "navigate",
    reasoning:
      "The navigation has a clearly labeled “Shop” link. That looks like the right place to start.",
    outcome: "ok",
  },
  {
    step: 2,
    action: "click",
    reasoning:
      "I can narrow the collection using the category filters. I’ll choose running shoes.",
    outcome: "ok",
  },
  {
    step: 3,
    action: "click",
    reasoning:
      "The product page shows the price and available sizes together. I can choose my usual size.",
    outcome: "ok",
  },
  {
    step: 4,
    action: "click",
    reasoning:
      "The “Add to cart” button is easy to find, and the confirmation tells me it worked.",
    outcome: "ok",
  },
];
function success(
  score: number,
  summary: string,
  steps = shoppingSteps,
): Result {
  return {
    success: true,
    score,
    summary,
    score_justification:
      score >= 9
        ? "Clear labels and immediate feedback kept the task short and easy to verify."
        : "The goal was completed, but an extra navigation step and unclear secondary labels added effort.",
    steps,
  };
}
const ids = fallbackPersonas.map((p) => p.id);
const featuredDemoRuns: Run[] = [
  {
    id: "demo-1",
    url: "https://www.nike.com",
    task: "Find a product and add it to cart",
    personas: ids,
    status: "completed",
    session_viewer_urls: {},
    errors: {},
    results: {
      first_time: success(
        9,
        "Found the running shoes, selected a size, and added a pair to the cart in four actions.",
      ),
      power_user: success(
        10,
        "Used category filters to find a product and add it to the cart in four direct actions.",
      ),
      elderly: {
        success: false,
        summary:
          "The size picker became hidden after enlarging the page. The agent could not choose a size and complete the task.",
        failure_reason: "no_progress",
        steps: [
          {
            step: 1,
            action: "zoom",
            reasoning:
              "The text is difficult to read. I’ll enlarge the page to 150%.",
            outcome: "ok",
            value: "150",
          },
          {
            step: 2,
            action: "click",
            reasoning:
              "I found a pair I like, but I can’t see where to choose my size.",
            outcome: "Size selection not reachable at 150% zoom",
          },
        ],
      },
      mobile_user: success(
        10,
        "Used the responsive product grid, chose a size, and added the item without losing the primary action.",
      ),
      accessibility_advocate: success(
        10,
        "Moved through labeled controls in a predictable order and reached the cart with clear feedback.",
      ),
      privacy_conscious: success(
        9,
        "Reviewed the product and checkout context before adding the item, with only a small amount of extra scanning.",
      ),
    },
  },
  {
    id: "demo-2",
    url: "https://www.notion.so",
    task: "Create an account and get started",
    personas: ids,
    status: "completed",
    session_viewer_urls: {},
    errors: {},
    results: Object.fromEntries(
      ids.map((id, i) => [
        id,
        id === "privacy_conscious"
          ? blockedDemoResult(
              7.2,
              "Create an account and get started",
              id,
              "The sign-up flow required profile details before explaining how the information would be used.",
            )
          : success(
              [9, 9, 8, 9, 10, 9][i],
              "Created an account and reached the welcome screen. Progress indicators made the onboarding steps easier to follow.",
              [
                {
                  step: 1,
                  action: "navigate",
                  reasoning: "The homepage has a visible “Get started” button.",
                  outcome: "ok",
                },
                {
                  step: 2,
                  action: "fill",
                  reasoning:
                    "The form labels clearly explain the required information.",
                  outcome: "ok",
                },
                {
                  step: 3,
                  action: "click",
                  reasoning:
                    "The welcome screen confirms that the sample account was created.",
                  outcome: "ok",
                },
              ],
            ),
      ]),
    ),
  },
  {
    id: "demo-3",
    url: "https://docs.github.com",
    task: "Find the API quickstart guide",
    personas: ["first_time", "power_user"],
    status: "completed",
    session_viewer_urls: {},
    errors: {},
    results: {
      first_time: blockedDemoResult(
        6.8,
        "Find the API quickstart guide",
        "first_time",
        "The quickstart was nested under similarly named documentation sections, and the first-time agent could not confirm the right path.",
      ),
      power_user: success(
        10,
        "Used documentation search to reach the API quickstart directly.",
        [
          {
            step: 1,
            action: "fill",
            reasoning: "Search looks like the quickest route to the API guide.",
            outcome: "ok",
          },
          {
            step: 2,
            action: "click",
            reasoning: "The first result matches the exact guide I need.",
            outcome: "ok",
          },
        ],
      ),
    },
  },
];

export const demoRuns: Run[] = [
  ...featuredDemoRuns,
  ...additionalDemoSpecs.map(buildDemoRun),
];
