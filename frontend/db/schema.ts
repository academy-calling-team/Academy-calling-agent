import { sqliteTable, text } from 'drizzle-orm/sqlite-core';
export const members = sqliteTable('members', {
  userId: text('user_id').primaryKey(),
  nickname: text('nickname').notNull(),
  createdAt: text('created_at').notNull(),
});
export const drafts = sqliteTable('drafts', {
  id: text('id').primaryKey(),
  userId: text('user_id').notNull().references(() => members.userId),
  payload: text('payload').notNull(),
  createdAt: text('created_at').notNull(),
});
