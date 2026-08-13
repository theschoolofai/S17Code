# The A2UI component catalog

23 component types. This list is closed: the validator rejects any
type not named here, and any property not listed for that type.

Property kinds: `text` literal string · `binding` a `{"$bind":"/pointer"}` into
the data model · `enum` one of a fixed set · `ref` a list of child component ids ·
`action` one of the four registered actions · `number` · `bool`

## A2UI Basic (15)

| type | properties |
| --- | --- |
| `Row` | `children` ref<br>`align` enum (start/center/end/stretch/baseline)<br>`justify` enum (start/center/end/spaceBetween/spaceAround) |
| `Column` | `children` ref |
| `List` | `children` ref |
| `Card` | `title` text<br>`children` ref |
| `Divider` | — |
| `Text` | `text` binding<br>`variant` enum (heading/subtitle/body/caption) |
| `Image` | `src` text<br>`alt` text |
| `TextField` | `label` text<br>`value` binding<br>`placeholder` text |
| `CheckBox` | `label` text<br>`checked` binding |
| `Slider` | `label` text<br>`value` binding<br>`min` number<br>`max` number |
| `InputChoice` | `label` text<br>`options` binding<br>`value` binding |
| `DateTime` | `label` text<br>`value` binding |
| `Button` | `label` text<br>`onPress` action |
| `Tabs` | `labels` text<br>`children` ref |
| `Modal` | `title` text<br>`children` ref<br>`open` binding |

## Custom extensions (8)

| type | properties |
| --- | --- |
| `BarChart` | `title` text<br>`data` binding<br>`xKey` text<br>`yKey` text |
| `Sparkline` | `data` binding<br>`tone` enum (neutral/good/warn/bad) |
| `StatTile` | `label` text<br>`value` binding<br>`unit` text<br>`delta` binding<br>`tone` enum (neutral/good/warn/bad) |
| `ProgressBar` | `value` binding<br>`max` number<br>`tone` enum (neutral/good/warn/bad) |
| `Timeline` | `title` text<br>`events` binding |
| `DataTable` | `columns` text<br>`rows` binding<br>`sortable` bool<br>`filterKey` text |
| `Notice` | `text` binding<br>`tone` enum (neutral/good/warn/bad) |
| `ApprovalCard` | `summary` binding<br>`params` binding<br>`confirm` action<br>`reject` action |

## Actions

A `Button`'s `onPress` and an `ApprovalCard`'s `confirm`/`reject` may name only:

- `approve`
- `reject`
- `request_data`
- `rerun`

There is no `submit`, no `reveal`, no `next`. Anything else is rejected.