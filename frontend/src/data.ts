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
  }[];
  access_checks?: { state: string; evidence: string[] }[];
}
export interface Run {
  id: string;
  url: string;
  task: string;
  personas: string[];
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
      "A fresh pair of eyes. Discovers your product one step at a time.",
    system_prompt: "",
  },
  {
    id: "power_user",
    name: "Power User",
    description:
      "Knows the conventions. Looks for the quickest way to get things done.",
    system_prompt: "",
  },
  {
    id: "elderly",
    name: "Older adult",
    description:
      "Takes their time. Values clear navigation and easy-to-read text.",
    system_prompt: "",
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
        ? "Clear labels and immediate feedback made the task straightforward with very little friction."
        : "The goal was completed, but an extra navigation step and unclear secondary labels added effort.",
    steps,
  };
}
const ids = fallbackPersonas.map((p) => p.id);
export const demoRuns: Run[] = [
  {
    id: "demo-1",
    url: "https://store.example.com",
    task: "Find a product and add it to cart",
    personas: ids,
    status: "completed",
    session_viewer_urls: {},
    errors: {},
    results: {
      first_time: success(
        9,
        "Found the running shoes, selected a size, and added a pair to the cart. The journey felt clear and reassuring.",
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
    },
  },
  {
    id: "demo-2",
    url: "https://app.example.com",
    task: "Create an account and get started",
    personas: ids,
    status: "completed",
    session_viewer_urls: {},
    errors: {},
    results: Object.fromEntries(
      ids.map((id, i) => [
        id,
        success(
          [8, 9, 7][i],
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
    url: "https://docs.example.com",
    task: "Find the API quickstart guide",
    personas: ["first_time", "power_user"],
    status: "completed",
    session_viewer_urls: {},
    errors: {},
    results: {
      first_time: success(
        8,
        "Found the quickstart under the “Developers” navigation item after exploring the documentation.",
        [
          {
            step: 1,
            action: "click",
            reasoning:
              "I’ll try the Developers link to find the documentation.",
            outcome: "ok",
          },
          {
            step: 2,
            action: "click",
            reasoning:
              "The getting started section includes an API quickstart.",
            outcome: "ok",
          },
        ],
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
