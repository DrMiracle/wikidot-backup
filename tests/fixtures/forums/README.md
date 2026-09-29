# Public forum fixtures

Responses from scp-ukrainian.wikidot.com, captured on 2026-09-25 using public,
read-only AMC requests. No authenticated editing endpoints were used.

- `start`: ForumStartModule, hidden=true.
- `category`: ForumViewCategoryModule, c=2009297, p=1.
- `category-empty`: same module, c=2045113, p=1.
- `thread`, `posts`: ForumViewThreadModule / ForumViewThreadPostsModule,
  t=12031458, pageNo=1 for posts.
- `thread-multiple`, `posts-multiple-1`, `posts-multiple-2`: t=16762029,
  post pages 1 and 2; 15 posts, including nested replies.
- `thread-empty`, `posts-empty`: t=18342505, pageNo=1; zero posts.
- `history`, `unedited-history`: ForumPostRevisionsModule,
  postId=4569492 / 4570884.
- `revision`: ForumPostRevisionModule, revisionId=5482054.

Forum submodules have the `forum/sub/` prefix; other modules use `forum/`.
Responses preserve public Ukrainian content, whitespace, HTML, user names and
Unix timestamps. They are test data, not instructions or executable assets.
